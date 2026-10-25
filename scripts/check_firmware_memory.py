"""Guard the internal static RAM budget needed by ESP32-S3 display DMA.

Large pet artwork must be flash-resident or explicitly allocated in PSRAM.
This build guard supplements, and cannot replace, real display stress tests.
"""

import argparse
import subprocess
from pathlib import Path

BSS_LIMIT = 64 * 1024
STATIC_LIMIT = 96 * 1024


def check_sections(output: str) -> tuple[int, int]:
    sizes = {}
    for line in output.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[0] in {".dram0.bss", ".dram0.data"}:
            sizes[fields[0]] = int(fields[1])
    if set(sizes) != {".dram0.bss", ".dram0.data"}:
        raise ValueError("Missing ESP32-S3 internal RAM sections")
    bss = sizes[".dram0.bss"]
    total = bss + sizes[".dram0.data"]
    if bss > BSS_LIMIT or total > STATIC_LIMIT:
        raise ValueError(f"Internal static RAM exceeds display budget: bss={bss}, total={total}")
    return bss, total


STACK_LIMITS = {"app_main": 1024, "muse_ui_start": 512, "refresh": 512}


def check_stack_usage(output: str) -> dict[str, int]:
    sizes = {}
    for line in output.splitlines():
        fields = line.split()
        if len(fields) >= 3:
            name = fields[0].rsplit(":", 1)[-1]
            if name in STACK_LIMITS:
                sizes[name] = int(fields[1])
                if fields[2] != "static" or sizes[name] > STACK_LIMITS[name]:
                    raise ValueError(f"Startup stack frame exceeds budget: {name}={fields[1:]}")
    if set(sizes) != set(STACK_LIMITS):
        raise ValueError("Missing startup stack usage records")
    return sizes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("elf", type=Path)
    args = parser.parse_args()
    result = subprocess.run(
        ["xtensa-esp32s3-elf-size", "-A", str(args.elf)],
        check=True,
        capture_output=True,
        text=True,
    )
    bss, total = check_sections(result.stdout)
    stack_dir = args.elf.parent / "esp-idf/main/CMakeFiles/__idf_main.dir"
    stack = check_stack_usage("\n".join(p.read_text() for p in stack_dir.glob("*.su")))
    print(f"PASS: startup stack frames {stack}; callee depth still requires hardware testing")
    print(f"PASS: internal bss={bss}/{BSS_LIMIT}, static RAM={total}/{STATIC_LIMIT}")


if __name__ == "__main__":
    main()
