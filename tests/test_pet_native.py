"""Compile the exact ESP32-independent pet model with host C11; no mocks."""

import shutil
import subprocess
from pathlib import Path

import pytest


def test_native_pet_garden_state(tmp_path):
    cc = shutil.which("cc")
    if cc is None:
        pytest.skip("A C11 compiler is required for the native pet state test")
    root = Path(__file__).resolve().parents[1] / "firmware" / "esp32"
    binary = tmp_path / "pet_logic_test"
    build = subprocess.run(
        [
            cc,
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-pedantic",
            "-I",
            str(root / "main"),
            str(root / "main" / "muse_pet_logic.c"),
            str(root / "tests" / "pet_logic_test.c"),
            "-o",
            str(binary),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert build.returncode == 0, build.stderr
    run = subprocess.run([str(binary)], check=False, capture_output=True, text=True, timeout=5)
    assert run.returncode == 0, run.stderr
    assert "pet_logic native tests PASS" in run.stdout
