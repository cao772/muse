"""Low-cost, read-only macOS resources for the Muse USB status frame.

No root permissions or shell commands. Values are system-level estimates, not
Activity Monitor's proprietary memory-pressure graph or CPU temperature.
"""

from __future__ import annotations

import math
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path
from time import monotonic


def _command(args: list[str]) -> str:
    return subprocess.run(
        args, check=True, capture_output=True, text=True, timeout=3
    ).stdout


def _gib(value: float) -> float:
    return round(value / (1024**3), 1)


def _number(text: str, pattern: str) -> float | None:
    found = re.search(pattern, text, flags=re.IGNORECASE)
    return float(found.group(1)) if found else None


def _swap_gib(output: str) -> float | None:
    value = re.search(r"\bused\s*=\s*([0-9.]+)([KMG])", output, re.I)
    if not value:
        return None
    scale = {"K": 1024, "M": 1024**2, "G": 1024**3}[value.group(2).upper()]
    return _gib(float(value.group(1)) * scale)


def _vm_gib(output: str, physical: int) -> float | None:
    size = _number(output, r"page size of\s+(\d+)\s+bytes")
    if not size:
        return None
    pages = []
    for label in ("Pages active", "Pages wired down", "Pages occupied by compressor"):
        match = re.search(rf"^{re.escape(label)}:\s*([0-9]+)\.", output, re.M)
        if not match:
            return None
        pages.append(int(match.group(1)))
    return _gib(min(physical, sum(pages) * size))


def _cpu_pct(output: str) -> int | None:
    found = re.search(
        r"CPU usage:\s*([0-9.]+)%\s*user,\s*([0-9.]+)%\s*sys,",
        output,
        re.I,
    )
    if not found:
        return None
    result = float(found.group(1)) + float(found.group(2))
    return int(round(min(100.0, max(0.0, result))))


def _pressure(output: str) -> str:
    value = output.strip()
    return {"1": "normal", "2": "warning", "4": "critical"}.get(value, "unknown")


def _thermal(helper_path: str, command=_command) -> str:
    if not helper_path:
        return "unknown"
    path = Path(helper_path).expanduser()
    if not path.is_file() or not os.access(path, os.X_OK):
        return "unknown"
    try:
        value = command([str(path)]).strip().lower()
    except (OSError, subprocess.SubprocessError, UnicodeError, ValueError):
        return "unknown"
    return value if value in {"nominal", "fair", "serious", "critical"} else "unknown"


def _top_processes(output: str, *, order: str = "memory") -> list[dict]:
    result = []
    for line in output.splitlines():
        parts = line.strip().split(maxsplit=2)
        if len(parts) != 3:
            continue
        try:
            rss, cpu = int(parts[0]), float(parts[1])
        except ValueError:
            continue
        if rss < 0 or not math.isfinite(cpu) or not (0 <= cpu <= 1600):
            continue
        name = Path(parts[2]).name[:24]
        if not re.fullmatch(r"[\w .+()-]{1,24}", name):
            continue
        result.append({"name": name, "rss_mb": round(rss / 1024), "cpu": round(cpu, 1)})
    primary, secondary = ("cpu", "rss_mb") if order == "cpu" else ("rss_mb", "cpu")
    return sorted(
        result, key=lambda row: (row[primary], row[secondary]), reverse=True
    )[:3]


def unavailable_frame() -> dict:
    return {
        "status": "unavailable",
        "cpu_pct": None,
        "memory_total_gb": None,
        "memory_used_gb": None,
        "swap_used_gb": None,
        "disk_free_gb": None,
        "disk_total_gb": None,
        "pressure": "unknown",
        "thermal": "unknown",
        "alert": "unknown",
        "sample_age_seconds": None,
    }


class MacResourceMonitor:
    def __init__(self, *, thermal_helper="", show_processes=False, command=_command):
        self.thermal_helper = thermal_helper
        self.show_processes = show_processes
        self.command = command
        self.sampled_at: float | None = None
        self.frame = unavailable_frame()
        self._abnormal = 0
        self._normal = 0
        self._latched = "normal"

    def _run(self, args: list[str]) -> str | None:
        try:
            return self.command(args)
        except (OSError, subprocess.SubprocessError, UnicodeError, ValueError):
            return None

    def collect(self) -> dict:
        if platform.system() != "Darwin":
            self.frame = unavailable_frame()
            self.sampled_at = monotonic()
            return self.frame

        sysctl = "/usr/sbin/sysctl"
        mem = self._run([sysctl, "-n", "hw.memsize"])
        vm = self._run(["/usr/bin/vm_stat"])
        cpu = self._run(["/usr/bin/top", "-l", "1", "-n", "0"])
        swap = self._run([sysctl, "-n", "vm.swapusage"])
        pressure = self._run([sysctl, "-n", "kern.memorystatus_vm_pressure_level"])
        disk = None
        try:
            disk = shutil.disk_usage(Path.home())
        except OSError:
            pass

        try:
            total = int(mem.strip()) if mem else 0
        except ValueError:
            total = 0
        used = _vm_gib(vm, total) if vm and total > 0 else None
        cpu_pct = _cpu_pct(cpu) if cpu else None
        swap_used = _swap_gib(swap) if swap else None
        thermal = _thermal(self.thermal_helper, self.command)
        memory_pressure = _pressure(pressure or "")
        valid = total > 0 and used is not None

        if not valid:
            self.frame = unavailable_frame()
            self.sampled_at = monotonic()
            return self.frame

        free_gb = _gib(disk.free) if disk else None
        total_disk_gb = _gib(disk.total) if disk else None
        disk_fraction = disk.free / disk.total if disk and disk.total else None
        mem_fraction = used / _gib(total) if total else None

        urgent = (
            thermal == "critical"
            or memory_pressure == "critical"
            or (disk_fraction is not None and disk_fraction < 0.02)
        )
        abnormal = (
            thermal == "serious"
            or memory_pressure == "warning"
            or (cpu_pct is not None and cpu_pct >= 90)
            or (swap_used is not None and swap_used >= 8.0)
            or (disk_fraction is not None and disk_fraction < 0.05)
            or (mem_fraction is not None and mem_fraction >= 0.94)
        )
        # Three consecutive samples suppress transient CPU or cache spikes.
        if urgent:
            self._latched = "critical"
            self._normal = self._abnormal = 0
        elif abnormal:
            self._abnormal += 1
            self._normal = 0
            if self._abnormal >= 3:
                self._latched = "warning"
        else:
            self._normal += 1
            self._abnormal = 0
            if self._normal >= 3:
                self._latched = "normal"

        result = {
            "status": "available",
            "cpu_pct": cpu_pct,
            "memory_total_gb": _gib(total),
            "memory_used_gb": used,
            "swap_used_gb": swap_used,
            "disk_free_gb": free_gb,
            "disk_total_gb": total_disk_gb,
            "pressure": memory_pressure,
            "thermal": thermal,
            "alert": self._latched,
            "sample_age_seconds": 0,
        }
        if self.show_processes:
            ps = self._run(["/bin/ps", "-A", "-o", "rss=", "-o", "%cpu=", "-o", "comm="])
            result["top_memory_processes"] = _top_processes(ps or "")
            result["top_cpu_processes"] = _top_processes(ps or "", order="cpu")

        self.frame = result
        self.sampled_at = monotonic()
        return result

    def current(self) -> dict:
        if self.sampled_at is None:
            return unavailable_frame()
        age = monotonic() - self.sampled_at
        if age < 0 or age > 45 or self.frame["status"] == "unavailable":
            return unavailable_frame()
        return {**self.frame, "sample_age_seconds": min(45, int(age))}
