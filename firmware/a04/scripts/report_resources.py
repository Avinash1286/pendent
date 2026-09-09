"""Inspect real ARM ELF/config/source identities; does not flash or claim timing."""
import hashlib
import json
from pathlib import Path
import re
from elftools.elf.elffile import ELFFile

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parents[1]
BUILD = WORKSPACE / ".tools/a04-opus/arm"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    elf_path = BUILD / "zephyr/zephyr.elf"
    with elf_path.open("rb") as stream:
        elf = ELFFile(stream)
        if elf.header["e_machine"] != "EM_ARM" or elf.elfclass != 32:
            raise ValueError("Expected an actual 32-bit ARM ELF")
        symbols = elf.get_section_by_name(".symtab")
        symbol_values = {symbol.name: symbol["st_value"] for symbol in symbols.iter_symbols()}
        selected = {}
        for symbol in symbols.iter_symbols():
            if symbol.name in ("encoder_state", "capture", "archive", "journal", "nand_adapter", "probe_pages", "codec_stack", "input", "opus_encode", "opus_encoder_get_size", "aura_journal_export", "aura_w25n01gv_zephyr_init"):
                selected[symbol.name] = {"bytes": symbol["st_size"], "address": symbol["st_value"]}
        sections = [{"name": section.name, "bytes": section["sh_size"], "address": section["sh_addr"],
                     "type": section["sh_type"]} for section in elf.iter_sections()
                    if section["sh_flags"] & 2]
    config_path = BUILD / "zephyr/.config"
    config = config_path.read_text()
    for required in ("CONFIG_SOC_NRF52840", "CONFIG_MPU_STACK_GUARD", "CONFIG_INIT_STACKS", "CONFIG_THREAD_STACK_INFO"):
        if required + "=y" not in config:
            raise ValueError("Missing ARM probe configuration: " + required)
    if "CONFIG_BT=y" in config or "CONFIG_AUDIO_DMIC=y" in config:
        raise ValueError("Synthetic probe unexpectedly enables radio or microphone")
    compile_commands = (BUILD / "build.ninja").read_text()
    for required in ("-DFIXED_POINT=1", "-DDISABLE_FLOAT_API", "-DUSE_ALLOCA", "-DENABLE_HARDENING"):
        if required not in compile_commands:
            raise ValueError("Missing actual Opus compiler option: " + required)
    stack_entries = []
    for path in BUILD.rglob("*.su"):
        for line in path.read_text().splitlines():
            fields = line.split("\t")
            if len(fields) == 3:
                stack_entries.append({"function": fields[0].rsplit(":", 1)[-1],
                                      "compiler_reported_bytes": int(fields[1]), "classification": fields[2]})
    source_hashes = {}
    for folder in ("src", "include", "cmake"):
        for path in (ROOT / folder).rglob("*"):
            if path.is_file():
                source_hashes[path.relative_to(ROOT).as_posix()] = sha(path)
    for name in ("CMakeLists.txt", "prj.conf", "dependencies/opus-1.6.1.json"):
        source_hashes[name] = sha(ROOT / name)
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
        "purpose": "A04 codec, AUR3, packed journal and retained SPI adapter MCU ABI/resource probe with volatile synthetic NAND; not wearable firmware",
        "zephyr": "4.2.0", "sdk": "0.17.2", "opus": "1.6.1",
        "memory_regions": {name: {"used_bytes": used, "capacity_bytes": capacities[name]}
                           for name, used in memories.items()},
        "memory_evidence": "Actual ELF _flash_used and _image_ram_size symbols, checked against configured capacities",
        "symbols": selected,
        "allocated_sections": sections,
        "stack_analysis": {"translation_units_with_reports": len(list(BUILD.rglob('*.su'))),
                           "largest_reported_functions": sorted(stack_entries, key=lambda x: x['compiler_reported_bytes'], reverse=True)[:15],
                           "dynamic_functions": sum("dynamic" in x["classification"] for x in stack_entries),
                           "limitation": "Reports include compiled library functions later removed by linker GC. Per-function static lower bounds do not sum to a runtime stack high-water; alloca requires physical measurement."},
        "artifacts": {f"zephyr.{suffix}": {"bytes": (BUILD / f"zephyr/zephyr.{suffix}").stat().st_size,
                                           "sha256": sha(BUILD / f"zephyr/zephyr.{suffix}")}
                      for suffix in ("elf", "hex", "bin", "map")},
        "config_sha256": sha(config_path),
        "source_sha256": source_hashes,
        "not_verified": ["physical execution", "stack high-water", "encode deadline", "power/current", "PDM input",
                         "flash commit latency", "concurrent BLE", "final A04 board mapping", "signed boot/OTA"],
    }
    (ROOT / "verification/arm-resources.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": report["status"], "memory_regions": report["memory_regions"], "symbols": selected}, indent=2))


if __name__ == "__main__":
    main()
