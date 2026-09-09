"""Inspect real ARM ELF/config/source identities; does not flash or claim timing.

To bind a build to both input boundaries, run --capture-inputs PATH immediately
before the existing ARM build, then --inputs PATH after it. The ordinary report
invocation remains useful but explicitly reports when no before snapshot exists.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
from elftools.elf.elffile import ELFFile

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parents[1]
BUILD = WORKSPACE / ".tools/a04-opus/arm"
TRANSFER_APIS = (
    "aura_transfer_init", "aura_transfer_session_begin", "aura_transfer_session_end",
    "aura_transfer_cancel_work", "aura_transfer_submit", "aura_transfer_step",
    "aura_transfer_copy_response", "aura_transfer_copy_fragment", "aura_transfer_response_sent",
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_identities():
    hashes = {}
    for folder in ("src", "include", "cmake", "drivers"):
        for path in (ROOT / folder).rglob("*"):
            if (path.is_file() and path.suffix not in (".pyc", ".log") and
                    "__pycache__" not in path.parts and "out" not in path.parts):
                hashes[path.relative_to(ROOT).as_posix()] = sha(path)
    for name in ("CMakeLists.txt", "Kconfig", "prj.conf", "scripts/build.ps1", "scripts/report_resources.py", "dependencies/opus-1.6.1.json"):
        hashes[name] = sha(ROOT / name)
    return hashes


def compiler_identity():
    compiler = WORKSPACE / ".tools/zephyr/zephyr-sdk-0.17.2/arm-zephyr-eabi/bin/arm-zephyr-eabi-gcc.exe"
    result = subprocess.run([str(compiler), "--version"], text=True, capture_output=True, timeout=15, check=True)
    return {"path": compiler.relative_to(WORKSPACE).as_posix(), "sha256": sha(compiler),
            "version": result.stdout.splitlines()}


def dependency_identity():
    lock = json.loads((ROOT / "dependencies/opus-1.6.1.json").read_text())
    directory = ROOT / "third_party" / lock["directory"]
    for name, expected in lock["files"].items():
        if sha(directory / name) != expected:
            raise ValueError("Actual Opus source differs from lock: " + name)
    return {"version": lock["version"], "archive_sha256": lock["sha256"],
            "lock_sha256": sha(ROOT / "dependencies/opus-1.6.1.json"), "checked_files": len(lock["files"])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-inputs", type=Path)
    parser.add_argument("--inputs", type=Path)
    args = parser.parse_args()
    if args.capture_inputs and args.inputs:
        parser.error("Use either --capture-inputs or --inputs")
    current_sources = source_identities()
    current_compiler = compiler_identity()
    current_dependency = dependency_identity()
    if args.capture_inputs:
        args.capture_inputs.parent.mkdir(parents=True, exist_ok=True)
        snapshot = {"captured_at_utc": datetime.now(timezone.utc).isoformat(),
                    "source_sha256": current_sources, "compiler": current_compiler,
                    "Opus_dependency": current_dependency,
                    "build_command": ["pwsh.exe", "-NoProfile", "-File", "firmware/a04/scripts/build.ps1", "-Mode", "arm"],
                    "build_environment": {"CMAKE_BUILD_PARALLEL_LEVEL": "2"},
                    "scope": "Before ARM-only DK resource build; no host/golden regeneration, flashing or physical execution"}
        args.capture_inputs.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8", newline="\n")
        print("Captured ARM inputs: " + str(args.capture_inputs))
        return
    input_evidence = {"status": "before_snapshot_not_supplied", "source_comparison": "post-build snapshot only"}
    if args.inputs:
        snapshot = json.loads(args.inputs.read_text())
        for key, actual in (("source_sha256", current_sources), ("compiler", current_compiler), ("Opus_dependency", current_dependency)):
            if snapshot[key] != actual:
                raise ValueError("ARM build inputs changed after capture: " + key)
        input_evidence = {"status": "inputs_equal_before_and_after_build", "snapshot": str(args.inputs),
                          "snapshot_sha256": sha(args.inputs), "captured_at_utc": snapshot["captured_at_utc"],
                          "checked_at_utc": datetime.now(timezone.utc).isoformat(),
                          "build_command": snapshot["build_command"], "build_environment": snapshot["build_environment"]}
    elf_path = BUILD / "zephyr/zephyr.elf"
    with elf_path.open("rb") as stream:
        elf = ELFFile(stream)
        if elf.header["e_machine"] != "EM_ARM" or elf.elfclass != 32:
            raise ValueError("Expected an actual 32-bit ARM ELF")
        symbols = elf.get_section_by_name(".symtab")
        symbol_values = {symbol.name: symbol["st_value"] for symbol in symbols.iter_symbols()}
        selected = {}
        for symbol in symbols.iter_symbols():
            if symbol.name in ("encoder_state", "recorder", "audio_adapter", "journal", "nand_adapter", "probe_pages", "codec_stack", "input", "opus_encode", "opus_encoder_get_size", "aura_journal_export", "aura_w25n01gv_zephyr_init", "aura_dmic_health_get", "aura_audio_zephyr_begin", "aura_audio_zephyr_reader_step", "aura_audio_zephyr_service", "aura_recorder_consume", "release_context", "control_ledger", "aura_release_authenticate", "aura_release_sign", "aura_release_validate_next", "aura_control_open", "aura_control_provision", "aura_control_load", "aura_control_store",
                               "storage_owner", "storage_snapshot", "aura_storage_open", "aura_storage_provision",
                               "aura_storage_prepare_capture", "aura_storage_cancel_prepared", "aura_storage_request_release",
                               "aura_storage_release_step", "aura_storage_capture_id",
                               "aura_w25n01gv_zephyr_configure_control", "aura_w25n01gv_zephyr_control_io"):
                selected[symbol.name] = {"bytes": symbol["st_size"], "address": symbol["st_value"]}
            if symbol.name in (*TRANSFER_APIS, "transfer_owner"):
                selected[symbol.name] = {"bytes": symbol["st_size"], "address": symbol["st_value"],
                                         "type": symbol["st_info"]["type"]}
        for name in TRANSFER_APIS:
            if name not in selected or selected[name]["bytes"] == 0 or selected[name]["type"] != "STT_FUNC":
                raise ValueError("Missing actual linked transfer API function: " + name)
        if ("transfer_owner" not in selected or selected["transfer_owner"]["bytes"] <= 0
                or selected["transfer_owner"]["type"] != "STT_OBJECT"):
            raise ValueError("Missing actual statically allocated ARM transfer owner")
        required_storage = ("storage_owner", "storage_snapshot", "aura_storage_open", "aura_storage_provision",
                            "aura_storage_prepare_capture", "aura_storage_cancel_prepared", "aura_storage_request_release",
                            "aura_storage_release_step", "aura_storage_capture_id",
                            "aura_w25n01gv_zephyr_configure_control", "aura_w25n01gv_zephyr_control_io")
        if any(name not in selected or selected[name]["bytes"] == 0 for name in required_storage):
            raise ValueError("Missing linked storage owner/interface reservation")
        if selected["storage_snapshot"]["bytes"] != 45408:
            raise ValueError("Missing actual maximum storage snapshot reservation")
        sections = [{"name": section.name, "bytes": section["sh_size"], "address": section["sh_addr"],
                     "type": section["sh_type"]} for section in elf.iter_sections()
                    if section["sh_flags"] & 2]
    config_path = BUILD / "zephyr/.config"
    config = config_path.read_text()
    for required in ("CONFIG_SOC_NRF52840", "CONFIG_MPU_STACK_GUARD", "CONFIG_INIT_STACKS", "CONFIG_THREAD_STACK_INFO", "CONFIG_AURA_DMIC_NRFX_PDM", "CONFIG_AUDIO_DMIC"):
        if required + "=y" not in config:
            raise ValueError("Missing ARM probe configuration: " + required)
    if "CONFIG_BT=y" in config or "CONFIG_AUDIO_DMIC_NRFX_PDM=y" in config:
        raise ValueError("DK integration probe unexpectedly enables radio or the competing stock DMIC")
    dts = (BUILD / "zephyr/zephyr.dts").read_text()
    if 'compatible = "aura,nrf-pdm"' not in dts or 'aura_dk_pdm_default' not in dts:
        raise ValueError("Missing explicit custom-driver DK test binding")
    compile_commands = (BUILD / "build.ninja").read_text()
    for required in ("-DFIXED_POINT=1", "-DDISABLE_FLOAT_API", "-DUSE_ALLOCA", "-DENABLE_HARDENING"):
        if required not in compile_commands:
            raise ValueError("Missing actual Opus compiler option: " + required)
    stack_entries = []
    transfer_stack_entries = []
    for path in BUILD.rglob("*.su"):
        for line in path.read_text().splitlines():
            fields = line.split("\t")
            if len(fields) == 3:
                entry = {"function": fields[0].rsplit(":", 1)[-1],
                         "compiler_reported_bytes": int(fields[1]), "classification": fields[2]}
                stack_entries.append(entry)
                if "aura_transfer" in path.name:
                    transfer_stack_entries.append(entry)
    if not transfer_stack_entries:
        raise ValueError("Missing compiler stack-usage report for transfer implementation")
    # ELF linker symbols remain valid on a no-op rebuild where the linker does
    # not print a new memory table. They agree with the full build's table.
    capacities = {}
    for region, option in (("FLASH", "CONFIG_FLASH_SIZE"), ("RAM", "CONFIG_SRAM_SIZE")):
        match = re.search(r"^" + option + r"=(\d+)$", config, re.M)
        if not match:
            raise ValueError("Missing memory size: " + option)
        capacities[region] = int(match[1]) * 1024
    memories = {"FLASH": symbol_values["_flash_used"], "RAM": symbol_values["_image_ram_size"]}
    if any(not 0 < used < capacities[name] for name, used in memories.items()):
        raise ValueError("Invalid or overflowing linker memory region")
    report = {
        "status": "ARM_cross_compiled_not_executed",
        "target": "nrf52840dk/nrf52840",
        "purpose": "DK-only A04 recorder/Opus/NAND/SPI/audio-adapter/custom-DMIC/storage-owner/transfer-owner integration compile; synthetic PCM and volatile NAND, not wearable firmware",
        "authority_binding": "Function/ABI retention only; zero-initialized auth/control/storage objects have no key enrollment, control-block configuration or privileged audio erase callback. A real 45408-byte maximum AST1 caller snapshot is reserved alongside the storage owner and W25N control interface functions.",
        "peripheral_binding": "DK-only P0.30 CLK/P0.31 DIN pinctrl initializes at boot; probe never enables microphone power or starts a physical PDM stream",
        "transfer_binding": {"state": "Uninitialized static ABI/resource reservation only; no transfer API is invoked",
                             "owner_bytes": selected["transfer_owner"]["bytes"], "retained_API_symbols": list(TRANSFER_APIS),
                             "authentication": "No trusted authorization result, session, key or enrollment is configured",
                             "radio": "CONFIG_BT disabled; no GATT service or notification delivery exists in this probe"},
        "devicetree_sha256": sha(BUILD / "zephyr/zephyr.dts"),
        "zephyr": "4.2.0", "sdk": "0.17.2", "opus": "1.6.1",
        "memory_regions": {name: {"used_bytes": used, "capacity_bytes": capacities[name],
                                   "remaining_bytes": capacities[name] - used,
                                   "used_percent": round(100 * used / capacities[name], 3)}
                           for name, used in memories.items()},
        "memory_evidence": "Actual ELF _flash_used and _image_ram_size symbols, checked against configured capacities",
        "symbols": selected,
        "allocated_sections": sections,
        "stack_analysis": {"translation_units_with_reports": len(list(BUILD.rglob('*.su'))),
                           "largest_reported_functions": sorted(stack_entries, key=lambda x: x['compiler_reported_bytes'], reverse=True)[:15],
                           "dynamic_functions": sum("dynamic" in x["classification"] for x in stack_entries),
                           "transfer_implementation_functions": transfer_stack_entries,
                           "limitation": "Reports include compiled library functions later removed by linker GC. Per-function static lower bounds do not sum to a runtime stack high-water; alloca requires physical measurement."},
        "artifacts": {f"zephyr.{suffix}": {"bytes": (BUILD / f"zephyr/zephyr.{suffix}").stat().st_size,
                                           "sha256": sha(BUILD / f"zephyr/zephyr.{suffix}")}
                      for suffix in ("elf", "hex", "bin", "map")},
        "config_sha256": sha(config_path),
        "source_sha256": current_sources,
        "input_binding": input_evidence,
        "compiler": current_compiler,
        "Opus_dependency": current_dependency,
        "build_transcript_sha256": sha(ROOT / "verification/arm-build.txt"),
        "not_verified": ["physical execution", "stack high-water", "encode deadline", "power/current", "PDM input",
                         "flash commit latency", "concurrent BLE", "final A04 board mapping", "signed boot/OTA",
                         "transfer command execution on ARM", "authentication/enrollment", "GATT or phone transfer"],
    }
    if source_identities() != current_sources:
        raise ValueError("Sources changed while inspecting ARM resources")
    (ROOT / "verification/arm-resources.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": report["status"], "memory_regions": report["memory_regions"], "symbols": selected}, indent=2))


if __name__ == "__main__":
    main()
