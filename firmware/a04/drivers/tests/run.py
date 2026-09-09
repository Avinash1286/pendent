"""Compile production PDM lifecycle/callback code against fault-injection boundaries."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
DRIVERS = HERE.parent
OUT = HERE / "out"
ZIG = ROOT / ".tools/zephyr/venv/Lib/site-packages/ziglang/zig.exe"


def digest(path: Path) -> dict[str, str]:
    data = path.read_bytes()
    return {
        "sha256": sha256(data).hexdigest(),
        "lf_normalized_sha256": sha256(data.replace(b"\r\n", b"\n")).hexdigest(),
    }


def main() -> None:
    OUT.mkdir(exist_ok=True)
    command = [str(ZIG), "cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
               "-I" + str(DRIVERS.parent / "include"), str(HERE / "host_driver.c"),
               "-o", str(OUT / "host_driver.exe")]
    subprocess.run(command, check=True, cwd=ROOT)
    result = subprocess.run([str(OUT / "host_driver.exe")], check=True,
                            capture_output=True, text=True, cwd=ROOT)
    output = result.stdout.replace("\r\n", "\n")
    assert output.count("PASS ") == 20
    assert output.endswith("20 production-driver callback/lifecycle test groups passed\n")
    (HERE / "host-tests.txt").write_text(output, encoding="utf-8", newline="\n")
    sources = [DRIVERS / "aura_dmic_nrfx_pdm.c", DRIVERS.parent / "include/aura_dmic_health.h",
               HERE / "driver_shim.h", HERE / "host_driver.c", HERE / "run.py",
               DRIVERS / "CMakeLists.txt", DRIVERS / "Kconfig",
               DRIVERS / "dts/bindings/audio/aura,nrf-pdm.yaml",
               DRIVERS / "dts/bindings/vendor-prefixes.txt",
               DRIVERS / "probe/nrf52840dk_nrf52840.overlay"]
    upstream = [ROOT / ".tools/zephyr/zephyr/drivers/audio/dmic_nrfx_pdm.c",
                ROOT / ".tools/zephyr/modules/hal/nordic/nrfx/drivers/src/nrfx_pdm.c"]
    report = {
        "scope": "Production callback/lifecycle/read/health code; host kernel/HAL fault-injection boundaries",
        "physical_capture_tested": False,
        "clock_selection_configuration_and_devicetree": "Not host-tested; use actual Zephyr ARM compile",
        "passed_groups": 20,
        "compiler": subprocess.check_output([str(ZIG), "version"], text=True).strip(),
        "compile_flags": ["-std=c11", "-Wall", "-Wextra", "-Werror"],
        "sources": {p.relative_to(ROOT).as_posix(): digest(p) for p in sources},
        "pinned_upstream_sources": {p.relative_to(ROOT).as_posix(): digest(p) for p in upstream},
        "output": {"path": "firmware/a04/drivers/tests/host-tests.txt",
                   **digest(HERE / "host-tests.txt")},
    }
    (HERE / "verification.json").write_text(json.dumps(report, indent=2) + "\n",
                                             encoding="utf-8", newline="\n")
    print(output, end="")


if __name__ == "__main__":
    main()
