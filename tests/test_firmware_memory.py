"""Catch the static animation-RAM growth that starved real display DMA."""

import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "firmware_memory", Path(__file__).resolve().parents[1] / "scripts/check_firmware_memory.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_display_memory_budget_accepts_psram_art_build():
    assert MODULE.check_sections(".dram0.data 22060 0\n.dram0.bss 27600 0\n") == (27600, 49660)


def test_display_memory_budget_rejects_previous_static_art_regression():
    with pytest.raises(ValueError, match="exceeds display budget"):
        MODULE.check_sections(".dram0.data 22060 0\n.dram0.bss 124368 0\n")


def test_display_memory_budget_requires_real_esp32_sections():
    with pytest.raises(ValueError, match="Missing"):
        MODULE.check_sections(".bss 1024 0\n")
