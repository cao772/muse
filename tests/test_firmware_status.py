"""Compile the actual UI state reducer and exercise lifecycle transitions on the host."""

import subprocess
from pathlib import Path


def test_firmware_status_transitions(tmp_path):
    root = Path(__file__).resolve().parents[1]
    main = root / "firmware/esp32/main"
    binary = tmp_path / "status-test"
    subprocess.run(
        [
            "cc",
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(main),
            str(main / "muse_status.c"),
            str(root / "tests/firmware_status.c"),
            "-o",
            str(binary),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run([str(binary)], check=True, timeout=5)
