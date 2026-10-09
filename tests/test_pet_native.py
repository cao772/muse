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


def test_native_pet_animation(tmp_path):
    """Both pose selection and authored RGB565 sprites run as real native C11."""
    cc = shutil.which("cc")
    if cc is None:
        pytest.skip("A C11 compiler is required for the native sprite test")
    root = Path(__file__).resolve().parents[1] / "firmware" / "esp32"
    binary = tmp_path / "pet_animation_test"
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
            str(root / "main" / "muse_pet_animation.c"),
            str(root / "tests" / "pet_animation_test.c"),
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
    assert "pet_animation native tests PASS" in run.stdout


def test_pet_chinese_font_covers_all_ui_copy():
    """Check the converter's real exported glyph list against device UI copy."""
    import re

    root = Path(__file__).resolve().parents[1] / "firmware" / "esp32" / "main"
    ui = (root / "muse_ui.c").read_text()
    required = set(re.findall(r"[\u4e00-\u9fff]", ui))
    required.update("0123456789 ·")
    font = (root / "muse_pet_zh_18.c").read_text()
    exported = {chr(int(code, 16)) for code in re.findall(r"/\* U\+([0-9A-Fa-f]+)", font)}
    assert required <= exported, f"Missing pet glyphs: {required - exported}"
    title_font = (root / "muse_pet_zh_24.c").read_text()
    title_glyphs = {chr(int(code, 16)) for code in re.findall(r"/\* U\+([0-9A-Fa-f]+)", title_font)}
    assert set("十一的农场") <= title_glyphs
