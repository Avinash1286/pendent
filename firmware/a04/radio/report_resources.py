"""Bind the separate Bluetooth DK ELF to source/config/Opus and memory evidence.

Only loads this workspace's trusted Zephyr-generated edt.pickle. No flashing,
serial access, radio activation or physical/runtime authentication claims.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess

from elftools.elf.elffile import ELFFile

RADIO = Path(__file__).resolve().parent
A04 = RADIO.parent
ROOT = A04.parents[1]
BUILD = ROOT / '.tools/a04-radio/arm'
ZEPHYR = ROOT / '.tools/zephyr/zephyr'
EXPECTED_OBJECTS = {
    'snapshot': 45408, 'journal': 36008, 'storage': 208, 'nand': 4464,
    'encoder': 32768, 'recorder': 3568, 'audio': 21072, 'control': 4240,
    'reader_stack': 4160, 'storage_stack': 49216, 'transfer': 4440,
}
TRANSFER_APIS = (
    'aura_transfer_init', 'aura_transfer_session_begin', 'aura_transfer_session_end',
    'aura_transfer_cancel_work', 'aura_transfer_submit', 'aura_transfer_step',
    'aura_transfer_copy_response', 'aura_transfer_copy_fragment', 'aura_transfer_response_sent',
)
REQUIRED_FUNCTIONS = (*TRANSFER_APIS, 'main', 'opus_encode', 'aura_audio_zephyr_begin',
    'aura_audio_zephyr_reader_step', 'aura_audio_zephyr_service',
    'aura_audio_zephyr_privacy_cutoff', 'aura_w25n01gv_zephyr_init',
    'aura_storage_open', 'aura_storage_prepare_capture', 'aura_gatt_owner_tick',
    'aura_gatt_init', 'aura_pairing_init', 'aura_pairing_open', 'aura_pairing_close', 'aura_pairing_take',
    'z_impl_sys_csrand_get', 'entropy_nrf5_get_entropy',
    'bt_enable', 'bt_conn_set_security', 'bt_gatt_notify_cb', 'settings_load')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identities(paths):
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(set(paths))}


def source_paths():
    paths = []
    for folder in (RADIO, A04 / 'src', A04 / 'include', A04 / 'drivers', A04 / 'cmake'):
        for path in folder.rglob('*'):
            if not path.is_file() or any(part in {'verification', '__pycache__', 'out', 'tests'} for part in path.parts):
                continue
            if path.suffix in {'.c', '.h', '.py', '.ps1', '.overlay', '.conf', '.cmake', '.yaml', '.yml'} or path.name in {'CMakeLists.txt', 'Kconfig'}:
                paths.append(path)
    paths += list((A04 / 'bench/dts').rglob('*.yaml'))
    paths += [A04 / 'bench/boards/nrf52840dk_nrf52840.overlay', A04 / 'bench/report_resources.py',
              A04 / 'scripts/setup.py', A04 / 'dependencies/opus-1.6.1.json',
              ROOT / 'firmware/scripts/setup.ps1']
    paths += [ZEPHYR / name for name in ('VERSION', 'subsys/random/Kconfig',
              'subsys/random/random_entropy_device.c', 'drivers/entropy/Kconfig.nrf5',
              'drivers/entropy/entropy_nrf5.c', 'dts/arm/nordic/nrf52840.dtsi',
              'include/zephyr/kernel.h', 'subsys/bluetooth/host/Kconfig')]
    # These sources must exist before capture; scaffolding alone is not a build.
    for relative in ('src/main.c', 'src/aura_gatt_zephyr.c', 'include/aura_gatt_zephyr.h',
                     'src/aura_pairing_zephyr.c', 'include/aura_pairing_zephyr.h'):
        require((RADIO / relative).is_file(), 'Missing radio integration source: ' + relative)
    for relative in ('src/aura_session_auth.c', 'include/aura_session_auth.h'):
        require((A04 / relative).is_file(), 'Missing session authentication source: ' + relative)
    return sorted(set(paths))


def compiler_identity():
    path = ROOT / '.tools/zephyr/zephyr-sdk-0.17.2/arm-zephyr-eabi/bin/arm-zephyr-eabi-gcc.exe'
    run = subprocess.run([str(path), '--version'], capture_output=True, text=True, timeout=15, check=True)
    return {'path': str(path), 'sha256': sha(path), 'version': run.stdout.splitlines()}


def opus_identity():
    lock_path = A04 / 'dependencies/opus-1.6.1.json'
    lock = json.loads(lock_path.read_text(encoding='utf-8'))
    base = A04 / 'third_party' / lock['directory']
    require(all(sha(base / name) == digest for name, digest in lock['files'].items()), 'Opus source differs from pinned lock')
    return {'version': lock['version'], 'archive_sha256': lock['sha256'],
            'lock_sha256': sha(lock_path), 'checked_files': len(lock['files'])}


def inputs():
    return {'source_sha256': identities(source_paths()), 'compiler': compiler_identity(), 'opus': opus_identity()}


def cache_values():
    values = {}
    for line in (BUILD / 'CMakeCache.txt').read_text(encoding='utf-8').splitlines():
        match = re.fullmatch(r'([^/#][^:]*):[^=]+=(.*)', line)
        if match:
            values[match[1]] = match[2]
    require(Path(values['CMAKE_HOME_DIRECTORY']).resolve() == RADIO, 'Build belongs to another application')
    require(values['BOARD'] == 'nrf52840dk/nrf52840', 'Unexpected target')
    return values


def current_build(cache):
    run = subprocess.run([cache['CMAKE_MAKE_PROGRAM'], '-C', str(BUILD), '-n'],
                         text=True, capture_output=True, timeout=60, check=True)
    require('ninja: no work to do.' in run.stdout and not re.search(r'^\[\d+/', run.stdout, re.M),
            'Build is not current; rebuild before recording evidence')
    return run.stdout.strip()


def inspect_elf():
    with (BUILD / 'zephyr/zephyr.elf').open('rb') as stream:
        elf = ELFFile(stream)
        require(elf.elfclass == 32 and elf.header['e_machine'] == 'EM_ARM', 'Expected 32-bit ARM ELF')
        table = elf.get_section_by_name('.symtab')
        require(table is not None, 'Missing ELF symbols')
        by_name = {}
        for symbol in table.iter_symbols():
            if symbol.name and symbol['st_shndx'] != 'SHN_UNDEF':
                by_name.setdefault(symbol.name, []).append(symbol)
        selected = {}
        for name in (*EXPECTED_OBJECTS, *REQUIRED_FUNCTIONS, 'aura_gatt_state', 'session_auth', 'pairing', '_flash_used', '_image_ram_size'):
            expected_type = 'STT_FUNC' if name in REQUIRED_FUNCTIONS else (
                'STT_OBJECT' if name in EXPECTED_OBJECTS or name in ('aura_gatt_state', 'session_auth', 'pairing') else None)
            candidates = [s for s in by_name.get(name, []) if expected_type is None or s['st_info']['type'] == expected_type]
            require(len(candidates) == 1, 'Missing/ambiguous linked symbol of expected type: ' + name)
            symbol = candidates[0]
            selected[name] = {'bytes': symbol['st_size'], 'address': symbol['st_value'], 'type': symbol['st_info']['type']}
            if name in EXPECTED_OBJECTS:
                require(symbol['st_size'] == EXPECTED_OBJECTS[name] and symbol['st_info']['type'] == 'STT_OBJECT',
                        'Unexpected actual object size: ' + name)
            elif name in REQUIRED_FUNCTIONS:
                require(symbol['st_size'] > 0 and symbol['st_info']['type'] == 'STT_FUNC', 'Missing actual linked body: ' + name)
        require(selected['aura_gatt_state']['bytes'] > 0 and selected['aura_gatt_state']['type'] == 'STT_OBJECT', 'Missing GATT state allocation')
        require(selected['session_auth']['bytes'] > 0 and selected['session_auth']['type'] == 'STT_OBJECT', 'Missing session provider allocation')
        require(selected['pairing']['bytes'] > 0 and selected['pairing']['type'] == 'STT_OBJECT', 'Missing pairing policy allocation')
        pairing_object = BUILD / 'CMakeFiles/app.dir/src/aura_pairing_zephyr.c.obj'
        with pairing_object.open('rb') as object_stream:
            object_elf = ELFFile(object_stream)
            definitions = [s for s in object_elf.get_section_by_name('.symtab').iter_symbols()
                           if s.name == 'pairing' and s['st_shndx'] != 'SHN_UNDEF']
            require(len(definitions) == 1 and definitions[0]['st_info']['type'] == 'STT_OBJECT' and
                    definitions[0]['st_size'] == selected['pairing']['bytes'],
                    'Pairing allocation does not match its defining compiled object')
        selected['pairing'].update({'source': (RADIO / 'src/aura_pairing_zephyr.c').relative_to(ROOT).as_posix(),
                                   'defining_object': pairing_object.relative_to(ROOT).as_posix(),
                                   'defining_object_sha256': sha(pairing_object)})
        # Record whichever authentication APIs the real application calls, not an
        # artificial address-only retention that would imply exercised behavior.
        auth = {}
        for name, found in by_name.items():
            if name.startswith('aura_session_'):
                auth[name] = [{'bytes': s['st_size'], 'type': s['st_info']['type']} for s in found]
        require(auth, 'No session authentication implementation linked')
        absent = ['aura_storage_request_release', 'aura_storage_release_step']
        require(not any(name in by_name for name in absent), 'Radio target unexpectedly links audio release entry points')
        sections = [{'name': s.name, 'bytes': s['sh_size'], 'address': s['sh_addr']} for s in elf.iter_sections() if s['sh_flags'] & 2]
    return selected, auth, sections, absent


def inspect_audio_abi():
    # Verify the actual DWARF layout, rather than treating a changed C ABI as a
    # smaller/larger audio buffer. BT_HCI_HOST selects POLL, which inserts a
    # two-pointer sys_dlist_t poll_events member in k_msgq on 32-bit ARM.
    with (BUILD / 'zephyr/zephyr.elf').open('rb') as stream:
        dwarf = ELFFile(stream).get_dwarf_info()
        units = [cu for cu in dwarf.iter_CUs() if
                 cu.get_top_DIE().attributes['DW_AT_name'].value.decode().replace('\\', '/') ==
                 (RADIO / 'src/main.c').as_posix()]
        require(len(units) == 1, 'Missing unique main translation unit DWARF')
        layouts = {}
        for die in units[0].iter_DIEs():
            if die.tag != 'DW_TAG_structure_type' or 'DW_AT_name' not in die.attributes:
                continue
            name = die.attributes['DW_AT_name'].value.decode()
            if name not in ('k_msgq', 'k_mem_slab', 'aura_audio_zephyr') or 'DW_AT_byte_size' not in die.attributes:
                continue
            members = {m.attributes['DW_AT_name'].value.decode(): m.attributes['DW_AT_data_member_location'].value
                       for m in die.iter_children() if m.tag == 'DW_TAG_member'}
            layouts[name] = {'bytes': die.attributes['DW_AT_byte_size'].value, 'member_offsets': members}
        require(layouts['k_msgq']['bytes'] == 52 and
                layouts['k_msgq']['member_offsets']['poll_events'] == 40 and
                layouts['k_msgq']['member_offsets']['flags'] == 48 and
                layouts['k_mem_slab']['bytes'] == 32 and
                layouts['aura_audio_zephyr']['bytes'] == EXPECTED_OBJECTS['audio'] and
                layouts['aura_audio_zephyr']['member_offsets']['queue'] == 60 and
                layouts['aura_audio_zephyr']['member_offsets']['dma_memory'] == 112 and
                layouts['aura_audio_zephyr']['member_offsets']['queue_memory'] == 10352,
                'Audio/kernel object layout differs from the reviewed CONFIG_POLL ARM ABI')
    return {'actual_dwarf_layouts': layouts,
            'cause': 'BT_HCI_HOST selects CONFIG_POLL. Z_DECL_POLL_EVENT inserts an 8-byte sys_dlist_t poll_events at k_msgq offset 40; k_msgq is 52 bytes instead of 44, so the unchanged audio object is 21,072 bytes instead of the wired bench 21,064 bytes.',
            'audio_buffers_changed': False,
            'sources': ['.tools/zephyr/zephyr/subsys/bluetooth/host/Kconfig',
                        '.tools/zephyr/zephyr/include/zephyr/kernel.h',
                        'firmware/a04/include/aura_audio_zephyr.h']}


def inspect_config():
    text = (BUILD / 'zephyr/.config').read_text(encoding='utf-8')
    config = dict(re.findall(r'^(CONFIG_[A-Z0-9_]+)=(.*)$', text, re.M))
    enabled = ('CONFIG_SOC_NRF52840', 'CONFIG_BOARD_NRF52840DK', 'CONFIG_BT', 'CONFIG_BT_PERIPHERAL',
               'CONFIG_BT_SMP', 'CONFIG_BT_SMP_SC_ONLY', 'CONFIG_BT_SMP_SC_PAIR_ONLY',
               'CONFIG_BT_SMP_APP_PAIRING_ACCEPT', 'CONFIG_BT_SMP_ENFORCE_MITM',
               'CONFIG_BT_GATT_ENFORCE_SUBSCRIPTION', 'CONFIG_BT_SETTINGS', 'CONFIG_SETTINGS_NVS',
               'CONFIG_NVS', 'CONFIG_USE_DT_CODE_PARTITION', 'CONFIG_BT_RECV_WORKQ_BT', 'CONFIG_BT_HCI_HOST', 'CONFIG_POLL',
               'CONFIG_MPU_STACK_GUARD', 'CONFIG_INIT_STACKS', 'CONFIG_THREAD_STACK_INFO',
               'CONFIG_AURA_DMIC_NRFX_PDM', 'CONFIG_AUDIO_DMIC', 'CONFIG_SPI', 'CONFIG_GPIO',
               'CONFIG_ENTROPY_GENERATOR', 'CONFIG_ENTROPY_NRF5_RNG', 'CONFIG_ENTROPY_NRF5_BIAS_CORRECTION',
               'CONFIG_ENTROPY_DEVICE_RANDOM_GENERATOR', 'CONFIG_CSPRNG_ENABLED', 'CONFIG_HARDWARE_DEVICE_CS_GENERATOR')
    require(all(config.get(k) == 'y' for k in enabled), 'Required radio/security configuration missing')
    disabled = ('CONFIG_AUDIO_DMIC_NRFX_PDM', 'CONFIG_BT_FIXED_PASSKEY', 'CONFIG_BT_USE_DEBUG_KEYS',
                'CONFIG_BT_STORE_DEBUG_KEYS', 'CONFIG_BT_KEYS_OVERWRITE_OLDEST', 'CONFIG_BT_BONDABLE',
                'CONFIG_BT_GATT_DYNAMIC_DB', 'CONFIG_BT_EATT', 'CONFIG_BOOTLOADER_MCUBOOT',
                'CONFIG_USB_DEVICE_STACK', 'CONFIG_USB_DEVICE_STACK_NEXT', 'CONFIG_TEST_RANDOM_GENERATOR',
                'CONFIG_TEST_CSPRNG_GENERATOR', 'CONFIG_TIMER_RANDOM_GENERATOR',
                'CONFIG_XOSHIRO_RANDOM_GENERATOR', 'CONFIG_CTR_DRBG_CSPRNG_GENERATOR')
    require(all(config.get(k) != 'y' for k in disabled), 'Unexpected unsafe/different radio configuration')
    fixed = {'CONFIG_BT_MAX_CONN': 1, 'CONFIG_BT_MAX_PAIRED': 1, 'CONFIG_BT_ID_MAX': 1,
             'CONFIG_BT_L2CAP_TX_MTU': 247, 'CONFIG_BT_BUF_ACL_TX_SIZE': 251, 'CONFIG_BT_BUF_ACL_RX_SIZE': 251,
             'CONFIG_BT_ATT_TX_COUNT': 3, 'CONFIG_BT_BUF_ACL_TX_COUNT': 3, 'CONFIG_BT_ATT_PREPARE_COUNT': 0,
             'CONFIG_BT_RX_STACK_SIZE': 2048, 'CONFIG_MAIN_STACK_SIZE': 2048,
             'CONFIG_SYSTEM_WORKQUEUE_STACK_SIZE': 4096, 'CONFIG_HEAP_MEM_POOL_SIZE': 0,
             'CONFIG_SETTINGS_NVS_SECTOR_COUNT': 8, 'CONFIG_SETTINGS_NVS_SECTOR_SIZE_MULT': 1,
             'CONFIG_FLASH_LOAD_OFFSET': 0, 'CONFIG_FLASH_LOAD_SIZE': 0xf8000}
    require(all(int(config.get(k, '-1'), 0) == value for k, value in fixed.items()), 'Radio buffer/stack/partition sizing differs from review')
    selected = {k: v for k, v in config.items() if k.startswith(('CONFIG_BT_', 'CONFIG_MBEDTLS_', 'CONFIG_PSA_', 'CONFIG_SETTINGS_', 'CONFIG_NVS', 'CONFIG_FLASH_', 'CONFIG_SOC_FLASH_NRF_', 'CONFIG_MAIN_STACK_', 'CONFIG_SYSTEM_WORKQUEUE_STACK_', 'CONFIG_HEAP_', 'CONFIG_ENTROPY_', 'CONFIG_CSPRNG_', 'CONFIG_HARDWARE_DEVICE_CS_'))}
    return config, {'enabled_checks': enabled, 'disabled_checks': disabled, 'fixed': fixed, 'actual': selected}


def bench_helpers():
    spec = importlib.util.spec_from_file_location('aura_trusted_bench_resource_helpers', A04 / 'bench/report_resources.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.BUILD = BUILD
    module.ZEPHYR = ZEPHYR
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture-inputs', type=Path)
    parser.add_argument('--inputs', type=Path)
    args = parser.parse_args()
    require(bool(args.capture_inputs) != bool(args.inputs), 'Supply exactly one input capture/verification option')
    before = inputs()
    if args.capture_inputs:
        args.capture_inputs.parent.mkdir(parents=True, exist_ok=True)
        args.capture_inputs.write_text(json.dumps({'captured_at_utc': datetime.now(timezone.utc).isoformat(), **before}, indent=2) + '\n', encoding='utf-8')
        print('Captured radio ARM input identities: ' + str(len(before['source_sha256'])))
        return
    expected = json.loads(args.inputs.read_text(encoding='utf-8'))
    require(all(expected[key] == value for key, value in before.items()), 'Radio inputs changed since pre-build capture')
    cache = cache_values()
    dry = current_build(cache)
    generated_paths = [BUILD / 'CMakeCache.txt', BUILD / 'build.ninja', BUILD / 'compile_commands.json',
                       BUILD / 'zephyr/.config', BUILD / 'zephyr/zephyr.dts', BUILD / 'zephyr/edt.pickle']
    generated_paths += [BUILD / f'zephyr/zephyr.{suffix}' for suffix in ('elf', 'hex', 'bin', 'map')]
    generated_paths += sorted(BUILD.rglob('*.su'))
    generated_paths += [BUILD / 'CMakeFiles/app.dir/src/aura_pairing_zephyr.c.obj']
    generated = identities(generated_paths)
    symbols, auth, sections, absent = inspect_elf()
    audio_abi = inspect_audio_abi()
    config, configuration = inspect_config()
    helpers = bench_helpers()
    mapping = helpers.inspect_dts()
    with (BUILD / 'zephyr/edt.pickle').open('rb') as stream:
        edt = helpers.pickle.load(stream)
    entropy = edt.chosen_nodes['zephyr,entropy']
    require(entropy is edt.label2node['rng'] and entropy.status == 'okay' and
            entropy.compats == ['nordic,nrf-rng'], 'CSPRNG entropy source is not the enabled nRF hardware RNG')
    mapping['entropy'] = {'chosen': entropy.path, 'compatible': entropy.compats,
                          'source': 'sys_csrand_get / hardware entropy / nRF5 bias correction',
                          'scope': 'Resolved implementation only; no physical entropy or latency measurement'}
    code = edt.label2node['radio_code_partition']
    settings = edt.label2node['radio_settings_partition']
    require(edt.chosen_nodes['zephyr,code-partition'] is code and
            edt.chosen_nodes['zephyr,settings-partition'] is settings and
            code.parent is settings.parent and code.parent.parent is edt.label2node['flash0'] and
            len(code.regs) == 1 and code.regs[0].addr == 0 and code.regs[0].size == 0xf8000 and
            len(settings.regs) == 1 and settings.regs[0].addr == 0xf8000 and settings.regs[0].size == 0x8000,
            'Compiled internal code/settings partition boundary changed')
    stack = helpers.inspect_stack()
    main_source = (RADIO / 'src/main.c').read_text(encoding='utf-8')
    require(re.search(r'K_THREAD_STACK_DEFINE\(\s*storage_stack\s*,\s*49152\s*\)', main_source), '48KiB storage/codec stack reservation changed')
    require(re.search(r'K_THREAD_STACK_DEFINE\(\s*reader_stack\s*,\s*4096\s*\)', main_source), 'Reader stack reservation changed')
    require(re.search(r'\.erase_released\s*=\s*NULL', main_source), 'Missing explicit NULL audio erase capability')
    flash, ram = symbols['_flash_used']['address'], symbols['_image_ram_size']['address']
    require(0 < flash < 0xf8000 and 0 < ram < 262144, 'Radio image exceeds its reviewed FLASH/RAM region')
    current_build(cache)
    require(inputs() == before and identities(generated_paths) == generated, 'Inputs/outputs changed during report inspection')
    report = {'schema': 1, 'status': 'ARM_cross_compiled_not_executed', 'hardware_tested': False,
              'target': 'nrf52840dk/nrf52840', 'application': 'firmware/a04/radio',
              'purpose': 'Separate DK PDM/NAND/Opus storage owner plus actual Zephyr GATT/security integration; not wearable firmware.',
              'memory_regions': {'FLASH': {'used_bytes': flash, 'capacity_bytes': 0xf8000, 'remaining_bytes': 0xf8000-flash},
                                 'RAM': {'used_bytes': ram, 'capacity_bytes': 262144, 'remaining_bytes': 262144-ram}},
              'internal_settings_partition': {'offset': 0xf8000, 'bytes': 32768, 'nvs_sectors': 8,
                  'purpose': 'Bluetooth identity/bond/CCC state only; not storage-owner key provisioning'},
              'symbols': symbols, 'linked_session_authentication_symbols': auth, 'allocated_sections': sections,
              'audio_object_abi': audio_abi,
              'memory_limitation': 'Remaining RAM is linker-unreserved static capacity after all linked allocations and reserved stacks. It is not measured runtime stack headroom; no stack high-water, call-chain bound, or hardware timing has been established.',
              'configuration': configuration, 'compiled_peripheral_mapping': mapping, 'stack_analysis': stack,
              'audio_release_entry_points_absent': absent, 'source_sha256': before['source_sha256'],
              'compiler': before['compiler'], 'opus_dependency': before['opus'], 'generated_sha256': generated,
              'build_currentness': {'ninja_dry_run': dry, 'inputs_equal_before_and_after_build': True,
                  'prebuild_capture_sha256': sha(args.inputs), 'inspection_inputs_outputs_stable': True},
              'not_verified': ['physical radio/security pairing', 'owner enrollment/key custody', 'on-device HMAC session exchange',
                  'electrical PDM/NAND wiring', 'audio continuity during radio/NVS writes', 'runtime stack high-water',
                  'RF coexistence/throughput/latency', 'battery/thermal behavior', 'A04 wearable PCB', 'signed boot/OTA'],
              'scope': 'ELF, resolved config, compiled pin mapping and source binding only; no flash or runtime activation.'}
    output = RADIO / 'verification/arm-resources.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    os.replace(temporary, output)
    print(json.dumps({'status': report['status'], 'memory_regions': report['memory_regions'],
                      'gatt_state_bytes': symbols['aura_gatt_state']['bytes'],
                      'source_identities': len(before['source_sha256']), 'report': str(output)}, indent=2))


if __name__ == '__main__':
    main()
