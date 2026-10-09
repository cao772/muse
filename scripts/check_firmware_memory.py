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
    print(f"PASS: internal bss={bss}/{BSS_LIMIT}, static RAM={total}/{STATIC_LIMIT}")


if __name__ == "__main__":
    main()
