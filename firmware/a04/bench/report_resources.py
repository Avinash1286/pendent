"""Verify the separate DK bench ELF, compiled pin mapping and resource budget.

Reads only this workspace's trusted Zephyr-generated edt.pickle. Never point
pickle loading at downloaded/untrusted files. No flashing or hardware claims.
"""
from pathlib import Path
import hashlib
import json
import os
import pickle
import re
import subprocess
import sys

from elftools.elf.elffile import ELFFile

BENCH = Path(__file__).resolve().parent
A04 = BENCH.parent
ROOT = A04.parents[1]
BUILD = ROOT / ".tools/a04-bench/arm"
ZEPHYR = ROOT / ".tools/zephyr/zephyr"
OUTPUT = BENCH / "verification/arm-resources.json"
EXPECTED_OBJECTS = {
    "snapshot": 45408, "journal": 36008, "export_cursor": 3800, "storage": 208, "nand": 4464,
    "encoder": 32768, "recorder": 3568, "audio": 21064, "control": 4240,
    "reader_stack": 4160, "storage_stack": 49216,
}
REQUIRED_FUNCTIONS = (
    "main", "owner", "reader", "uart_input", "privacy_changed", "opus_encode",
    "aura_opus_state_bytes", "aura_opus_init_staged", "aura_opus_push", "aura_opus_finish",
    "aura_dmic_health_get", "aura_dmic_health_reset", "aura_audio_zephyr_init",
    "aura_audio_zephyr_begin", "aura_audio_zephyr_reader_step", "aura_audio_zephyr_service",
    "aura_audio_zephyr_request_stop", "aura_audio_zephyr_privacy_cutoff",
    "aura_recorder_start", "aura_recorder_consume", "aura_recorder_stop", "aura_recorder_interrupt",
    "aura_journal_mount", "aura_journal_invalidate_exports",
    "aura_journal_cursor_open", "aura_journal_cursor_verify_step", "aura_journal_cursor_seek",
    "aura_journal_cursor_read", "aura_journal_cursor_get_info", "aura_journal_cursor_cancel",
    "aura_w25n01gv_zephyr_init", "aura_w25n01gv_zephyr_io",
    "aura_w25n01gv_zephyr_configure_control", "aura_w25n01gv_zephyr_control_io",
    "aura_w25n01gv_init", "aura_w25n01gv_control_io",
    "aura_storage_open", "aura_storage_provision", "aura_storage_prepare_capture",
    "aura_storage_cancel_prepared", "aura_storage_capture_id",
    "aura_control_open", "aura_control_provision", "aura_control_load", "aura_control_store",
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identities(paths):
    return {path.relative_to(ROOT).as_posix(): sha(path) for path in sorted(set(paths))}


def cache_values():
    values = {}
    for line in (BUILD / "CMakeCache.txt").read_text().splitlines():
        match = re.fullmatch(r"([^/#][^:]*):[^=]+=(.*)", line)
        if match:
            values[match[1]] = match[2]
    require(Path(values["CMAKE_HOME_DIRECTORY"]).resolve() == BENCH,
            "ELF belongs to another application, not the separate bench")
    require(values["BOARD"] == "nrf52840dk/nrf52840", "Unexpected bench board")
    return values


def require_current_build(cache):
    # Ninja's dry run does not execute compiler/linker/regeneration commands.
    # This detects pending builds; file digests below also reject concurrent
    # changes. It does not defend against malicious timestamp/build tampering.
    result = subprocess.run([cache["CMAKE_MAKE_PROGRAM"], "-C", str(BUILD), "-n"],
                            capture_output=True, text=True, timeout=60, check=True)
    require("ninja: no work to do." in result.stdout and not re.search(r"^\[\d+/", result.stdout, re.M),
            "Bench build is not current; rebuild before recording evidence")
    return result.stdout.strip()


def source_paths():
    paths = []
    allowed = {".c", ".h", ".py", ".ps1", ".yaml", ".yml", ".overlay", ".conf", ".cmake", ".md", ".txt"}
    for directory in (BENCH, A04 / "src", A04 / "include", A04 / "drivers", A04 / "cmake"):
        for path in directory.rglob("*"):
            if not path.is_file() or any(part in {"verification", "__pycache__", "out"} for part in path.parts):
                continue
            if path.suffix in allowed or path.name in {"CMakeLists.txt", "Kconfig"}:
                paths.append(path)
    paths += [A04 / "dependencies/opus-1.6.1.json"]
    paths += [ROOT / "companion/src/aura_companion" / name for name in
              ("__init__.py", "files.py", "protocol.py", "protocol_v2.py", "release.py")]
    paths += [ROOT / "companion/pyproject.toml"]
    return sorted(set(paths))


def inspect_elf():
    with (BUILD / "zephyr/zephyr.elf").open("rb") as stream:
        elf = ELFFile(stream)
        require(elf.elfclass == 32 and elf.header["e_machine"] == "EM_ARM", "Expected a 32-bit ARM ELF")
        table = elf.get_section_by_name(".symtab")
        require(table is not None, "ELF symbol table is required")
        by_name = {}
        for symbol in table.iter_symbols():
            if symbol.name and symbol["st_shndx"] != "SHN_UNDEF":
                by_name.setdefault(symbol.name, []).append(symbol)
        selected = {}
        for name in (*EXPECTED_OBJECTS, *REQUIRED_FUNCTIONS, "_flash_used", "_image_ram_size"):
            require(len(by_name.get(name, [])) == 1, "Missing/ambiguous linked symbol: " + name)
            symbol = by_name[name][0]
            selected[name] = {"bytes": symbol["st_size"], "address": symbol["st_value"],
                              "type": symbol["st_info"]["type"]}
            if name in EXPECTED_OBJECTS:
                require(symbol["st_size"] == EXPECTED_OBJECTS[name] and symbol["st_info"]["type"] == "STT_OBJECT",
                        "Unexpected allocated object size: " + name)
            elif name in REQUIRED_FUNCTIONS:
                require(symbol["st_size"] > 0 and symbol["st_info"]["type"] == "STT_FUNC",
                        "Missing actual linked function body: " + name)
        absent = ["aura_storage_request_release", "aura_storage_release_step"]
        require(not any(name in by_name for name in absent), "Bench unexpectedly links audio release entry points")
        sections = [{"name": section.name, "bytes": section["sh_size"], "address": section["sh_addr"],
                     "type": section["sh_type"]} for section in elf.iter_sections() if section["sh_flags"] & 2]
    return selected, sections, absent


def inspect_config(cache):
    text = (BUILD / "zephyr/.config").read_text()
    config = dict(re.findall(r"^(CONFIG_[A-Z0-9_]+)=(.*)$", text, re.M))
    enabled = ("CONFIG_SOC_NRF52840", "CONFIG_BOARD_NRF52840DK", "CONFIG_MPU_STACK_GUARD",
               "CONFIG_INIT_STACKS", "CONFIG_THREAD_STACK_INFO", "CONFIG_AURA_DMIC_NRFX_PDM",
               "CONFIG_AUDIO_DMIC", "CONFIG_GPIO", "CONFIG_SPI", "CONFIG_HWINFO",
               "CONFIG_UART_INTERRUPT_DRIVEN", "CONFIG_UART_0_INTERRUPT_DRIVEN", "CONFIG_NRFX_SPIM3")
    require(all(config.get(name) == "y" for name in enabled), "Required bench configuration missing")
    disabled = ("CONFIG_BT", "CONFIG_AUDIO_DMIC_NRFX_PDM", "CONFIG_USB_DEVICE_STACK", "CONFIG_USB_DEVICE_STACK_NEXT")
    require(all(config.get(name) != "y" for name in disabled), "Unexpected radio, stock DMIC or MCU USB stack")
    require(config["CONFIG_HEAP_MEM_POOL_SIZE"] == "0", "Bench unexpectedly allocates a kernel heap")
    require(config["CONFIG_MAIN_STACK_SIZE"] == "2048", "Unexpected main stack allocation")
    commands = json.loads((BUILD / "compile_commands.json").read_text())
    main_commands = [item for item in commands if Path(item["file"]).resolve() == BENCH / "src/main.c"]
    require(len(main_commands) == 1 and "-Werror" in main_commands[0]["command"], "New main.c must compile with -Werror")
    opus_commands = [item for item in commands if "/opus-1.6.1/" in item["file"].replace("\\", "/")]
    require(opus_commands, "No actual Opus compilation commands")
    opus_flags = ("-DFIXED_POINT=1", "-DDISABLE_FLOAT_API", "-DUSE_ALLOCA", "-DENABLE_HARDENING")
    require(all(all(flag in item["command"] for flag in opus_flags) for item in opus_commands),
            "Unexpected actual Opus compiler profile")
    require(cache["OPUS_FIXED_POINT"] == "ON" and cache["OPUS_USE_ALLOCA"] == "ON", "Opus profile cache mismatch")
    return config, {"enabled": list(enabled), "disabled": list(disabled), "kernel_heap_bytes": 0,
                    "main_source_warnings_as_errors": True, "opus_translation_units": len(opus_commands),
                    "opus_flags_checked_on_every_command": list(opus_flags),
                    "warning_scope": "No warning-free claim for legacy A04 core or unchanged upstream Opus."}


def inspect_dts():
    sys.path.insert(0, str(ZEPHYR / "scripts/dts/python-devicetree/src"))
    # This exact local build output is trusted, unlike arbitrary supplied pickles.
    edt = pickle.loads((BUILD / "zephyr/edt.pickle").read_bytes())
    labels = edt.label2node
    gpio0, gpio1 = labels["gpio0"], labels["gpio1"]

    def pins(label, state):
        sets = [entry for entry in labels[label].pinctrls if entry.name == state]
        require(len(sets) == 1, f"Missing/ambiguous {label} {state} pinctrl")
        result = []
        for node in sets[0].conf_nodes:
            for group in node.children.values():
                if "psels" in group.props:
                    result.extend(group.props["psels"].val)
        return sorted(result)

    # NRF_PSEL encodes function in bits31:24 and port*32+pin in bits8:0.
    expected = {
        ("pdm0", "default"): [(20 << 24) | 30, (21 << 24) | 31],
        ("spi3", "default"): [(4 << 24) | 47, (5 << 24) | 45, (6 << 24) | 46],
        ("spi3", "sleep"): [(4 << 24) | 47, (5 << 24) | 45, (6 << 24) | 46],
        ("uart0", "default"): [6, (1 << 24) | 8, (2 << 24) | 5, (3 << 24) | 7],
        ("uart0", "sleep"): [6, (1 << 24) | 8, (2 << 24) | 5, (3 << 24) | 7],
    }
    pinctrl = {}
    for (label, state), values in expected.items():
        actual = pins(label, state)
        require(actual == sorted(values), f"Unexpected compiled {label}/{state} pins")
        pinctrl[f"{label}/{state}"] = actual
    require(labels["pdm0"].status == "okay" and labels["pdm0"].compats == ["aura,nrf-pdm"],
            "Missing custom monitored PDM driver binding")
    require(labels["pdm0"].props["clock-source"].val == "PCLK32M_HFXO", "Unexpected PDM clock source")
    require(labels["pdm0"].props["queue-size"].val == 4, "Unexpected PDM driver RX queue size")
    require(labels["spi3"].status == "okay" and labels["spi3"].compats == ["nordic,nrf-spim"],
            "Missing intended SPI3 controller")
    require(labels["uart0"].status == "okay" and labels["uart0"].props["current-speed"].val == 115200,
            "UART0 baud/status changed")
    require(edt.chosen_nodes["zephyr,console"] is labels["uart0"], "Console no longer uses preserved DK UART0")
    require(all(labels[name].status == "disabled" for name in ("spi1", "pwm0", "i2c1", "uart1")),
            "A conflicting default peripheral remains enabled")
    require(labels["bench_controls"].compats == ["aura,bench-controls"], "Controls need their dedicated passive binding")
    require(labels["bench_nand"].parent is labels["spi3"] and labels["bench_nand"].status == "okay" and
            labels["bench_nand"].compats == ["aura,bench-nand"] and labels["bench_nand"].regs[0].addr == 0 and
            labels["bench_nand"].props["spi-max-frequency"].val == 1000000,
            "Unexpected NAND device, CS index or frequency")
    gpio_bindings = {}
    for label, prop, controller, pin, flags in (
        ("spi3", "cs-gpios", gpio1, 12, 1),
        ("bench_controls", "mic-enable-gpios", gpio1, 3, 0),
        ("bench_controls", "privacy-gpios", gpio1, 4, 17),
    ):
        values = labels[label].props[prop].val
        require(len(values) == 1 and values[0].controller is controller and
                values[0].data == {"pin": pin, "flags": flags}, f"Unexpected {label}/{prop}")
        gpio_bindings[f"{label}/{prop}"] = {"port": 1 if controller is gpio1 else 0, "pin": pin, "flags": flags}
    led_node = edt.get_node("led0")
    led_gpio = led_node.props["gpios"].val
    require(len(led_gpio) == 1 and led_gpio[0].controller is gpio0 and led_gpio[0].data == {"pin": 13, "flags": 1},
            "Status LED no longer uses onboard active-low P0.13")
    return {"pinctrl_psels": pinctrl, "gpio_bindings": gpio_bindings, "status_led": "P0.13 active low",
            "nand_bus_hz": 1000000, "uart_baud": 115200, "console": labels["uart0"].path,
            "disabled_conflicts": ["spi1", "pwm0", "i2c1", "uart1"],
            "scope": "Compiled device-tree mapping; no electrical, timing or actual wiring validation."}


def inspect_source_policy():
    source = (BENCH / "src/main.c").read_text()
    verbs = sorted(set(re.findall(r'strcmp\(verb,\s*"([A-Z]+)"\)', source)))
    require(verbs == sorted(["INFO", "STATS", "STOP", "PROVISION", "OPEN", "LIST", "START", "EXPORT"]),
            "Bench command vocabulary changed and requires review")
    require(re.search(r"\.erase_released\s*=\s*NULL", source), "Missing explicit NULL audio erase capability")
    require(re.search(r"\.blocks\s*=\s*\{\s*1022\s*,\s*1023\s*\}", source), "Control pair changed")
    require(re.search(r"configure_control\(&nand,\s*1022,\s*1023\)", source), "W25N control pair changed")
    stacks = {}
    for name, usable in (("reader_stack", 4096), ("storage_stack", 49152)):
        require(re.search(r"K_THREAD_STACK_DEFINE\(\s*" + name + r"\s*,\s*" + str(usable) + r"\s*\)", source),
                "Reviewed thread stack request changed: " + name)
        stacks[name] = {"requested_usable_bytes": usable, "elf_reserved_bytes": EXPECTED_OBJECTS[name],
                        "guard_alignment_overhead_bytes": EXPECTED_OBJECTS[name] - usable}
    return verbs, stacks


def inspect_stack():
    paths = sorted(BUILD.rglob("*.su"))
    require(paths, "No compiler stack-usage reports")
    entries = []
    for path in paths:
        for line in path.read_text().splitlines():
            fields = line.split("\t")
            if len(fields) == 3:
                entries.append({"function": fields[0].rsplit(":", 1)[-1],
                                "compiler_reported_bytes": int(fields[1]), "classification": fields[2]})
    require(any("dynamic" in entry["classification"] for entry in entries), "Expected alloca stack reports absent")
    return {"translation_units_with_reports": len(paths),
            "largest_reported_functions": sorted(entries, key=lambda row: row["compiler_reported_bytes"], reverse=True)[:20],
            "dynamic_functions": sum("dynamic" in row["classification"] for row in entries),
            "limitation": "Compiler per-function static lower bounds include library functions removed by linker GC. They are not a call-chain bound or measured runtime stack high-water. Opus uses alloca; physical thread/ISR stack measurements remain required."}


def main():
    cache = cache_values()
    dry_run = require_current_build(cache)
    paths = source_paths()
    source_before = identities(paths)
    generated = [BUILD / "CMakeCache.txt", BUILD / "build.ninja", BUILD / "compile_commands.json",
                 BUILD / "zephyr/.config", BUILD / "zephyr/zephyr.dts", BUILD / "zephyr/edt.pickle"]
    generated += [BUILD / f"zephyr/zephyr.{suffix}" for suffix in ("elf", "hex", "bin", "map")]
    generated += sorted(BUILD.rglob("*.su"))
    generated_before = identities(generated)
    dependency = json.loads((A04 / "dependencies/opus-1.6.1.json").read_text())
    opus_root = A04 / "third_party" / dependency["directory"]
    opus_paths = [opus_root / name for name in dependency["files"]]
    opus_before = {path.relative_to(opus_root).as_posix(): sha(path) for path in opus_paths}
    require(opus_before == dependency["files"], "Restored Opus sources differ from the pinned manifest")
    symbols, sections, absent = inspect_elf()
    config, configuration = inspect_config(cache)
    mapping = inspect_dts()
    verbs, stacks = inspect_source_policy()
    stack_analysis = inspect_stack()
    memories = {}
    for region, symbol, option in (("FLASH", "_flash_used", "CONFIG_FLASH_SIZE"),
                                    ("RAM", "_image_ram_size", "CONFIG_SRAM_SIZE")):
        used, capacity = symbols[symbol]["address"], int(config[option]) * 1024
        require(0 < used < capacity, "Invalid/overflowing " + region + " linker region")
        memories[region] = {"used_bytes": used, "capacity_bytes": capacity, "remaining_bytes": capacity-used}
    require_current_build(cache)
    require(source_paths() == paths and identities(paths) == source_before,
            "Source inputs changed during inspection; no new evidence published")
    require(identities(generated) == generated_before, "Build outputs changed during inspection")
    require({path.relative_to(opus_root).as_posix(): sha(path) for path in opus_paths} == opus_before,
            "Opus sources changed during inspection")
    report = {
        "schema": 1, "status": "ARM_cross_compiled_not_executed", "hardware_tested": False,
        "target": "nrf52840dk/nrf52840", "application": "firmware/a04/bench",
        "purpose": "Separate USB-powered DK + external PDM/NAND wired bench application, not AURA wearable firmware.",
        "memory_regions": memories,
        "memory_evidence": "Actual ELF _flash_used/_image_ram_size symbols checked against configured capacities.",
        "symbols": symbols, "allocated_sections": sections, "thread_stacks": stacks,
        "configuration": configuration, "compiled_devicetree": mapping, "stack_analysis": stack_analysis,
        "command_scope": {"verbs": verbs, "reserved_control_blocks": [1022, 1023],
                          "audio_erase_callback": "NULL in reviewed source", "absent_elf_entry_points": absent,
                          "limitation": "Source vocabulary and linked-symbol checks establish this bench build's intended API scope. They are not a proof of authenticated transport, physical tamper resistance, secure key storage or general impossibility of flash erasure. Explicit provisioning/capture may erase verified blank audio blocks and recycle control blocks."},
        "export_scope": {"cursor_object_bytes": symbols["export_cursor"]["bytes"],
                         "journal_object_bytes": symbols["journal"]["bytes"],
                         "uart_data_max_bytes": 128, "cursor_seek_offset": 0,
                         "completion": "END EXPORT follows cursor EOF and final physical revalidation; DATA remains temporary until then.",
                         "limitation": "UART dispatch is still synchronous. Yielding between cursor steps does not implement command preemption, wire resume, Bluetooth, or measured physical latency."},
        "peripheral_behavior": "Cold boot probes/resets/configures NAND and scans factory/LUT markers. Explicit OPEN/PROVISION and START gate recording. UART uses the DK interface MCU; no nRF USB stack or Bluetooth is enabled.",
        "build_currentness": {"ninja_dry_run": dry_run, "input_and_output_hashes_stable_across_inspection": True,
                              "limitation": "Current local Ninja dependency state plus source/output hashes; not a reproducible-build or malicious-toolchain attestation."},
        "source_sha256": source_before, "generated_sha256": generated_before,
        "opus_dependency": {"version": dependency["version"], "manifest_sha256": sha(A04 / "dependencies/opus-1.6.1.json"),
                            "checked_files": len(opus_before), "all_match_pinned_manifest": True},
        "artifacts": {f"zephyr.{suffix}": {"bytes": (BUILD / f"zephyr/zephyr.{suffix}").stat().st_size,
                                           "sha256": generated_before[(BUILD / f"zephyr/zephyr.{suffix}").relative_to(ROOT).as_posix()]}
                      for suffix in ("elf", "hex", "bin", "map")},
        "not_verified": ["physical execution", "actual wiring and supply", "PDM/DAT electrical margins",
                         "physical privacy cutoff and backfeed", "DMA/audio continuity", "runtime stack high-water",
                         "Opus capture deadlines", "NAND program/erase latency and durability on hardware",
                         "battery/thermal/RF behavior", "A04 PCB mapping", "authenticated mobile transport", "signed boot/OTA"],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    os.replace(temporary, OUTPUT)
    print(json.dumps({"status": report["status"], "memory_regions": memories, "thread_stacks": stacks,
                      "source_identities": len(source_before), "generated_identities": len(generated_before),
                      "report": OUTPUT.relative_to(ROOT).as_posix()}, indent=2))


if __name__ == "__main__":
    main()
