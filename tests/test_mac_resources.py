from unittest.mock import patch

from integrations.mac_resources import (
    MacResourceMonitor,
    _cpu_pct,
    _pressure,
    _swap_gib,
    _top_processes,
    _vm_gib,
    unavailable_frame,
)

VM = """Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free:                               12000.
Pages active:                            330000.
Pages inactive:                          160000.
Pages speculative:                        20000.
Pages wired down:                        155000.
Pages occupied by compressor:            60000.
"""
TOP = "Processes: 560 total\nCPU usage: 42.5% user, 18.2% sys, 39.3% idle\n"
SWAP = "vm.swapusage: total = 4096.00M  used = 1024.00M  free = 3072.00M"


def fake(args):
    key = args[-1]
    if key == "hw.memsize":
        return "17179869184\n"
    if key == "vm.swapusage":
        return SWAP
    if key == "kern.memorystatus_vm_pressure_level":
        return "1\n"
    if "vm_stat" in args[0]:
        return VM
    if "top" in args[0]:
        return TOP
    if "ps" in args[0]:
        return (
            "1048576 125.4 /Applications/Codex.app/Contents/MacOS/Codex\n"
            "2048 0.1 /usr/bin/python3\n"
        )
    raise AssertionError(args)


def test_mac_parsers():
    assert _vm_gib(VM, 17179869184) == 8.3
    assert _cpu_pct(TOP) == 61
    assert _swap_gib(SWAP) == 1.0
    assert _pressure("2") == "warning"
    assert _pressure("garbled") == "unknown"
    assert _top_processes(fake(["/bin/ps"]))[0]["name"] == "Codex"
    assert _top_processes(fake(["/bin/ps"]), order="cpu")[0]["name"] == "Codex"


def test_monitor_read_only_mac_snapshot():
    with patch("integrations.mac_resources.platform.system", return_value="Darwin"):
        monitor = MacResourceMonitor(command=fake, show_processes=True)
        snapshot = monitor.collect()
    assert snapshot["status"] == "available"
    assert snapshot["cpu_pct"] == 61
    assert snapshot["memory_total_gb"] == 16.0
    assert snapshot["memory_used_gb"] == 8.3
    assert snapshot["thermal"] == "unknown"
    assert snapshot["pressure"] == "normal"
    assert snapshot["top_memory_processes"][0]["name"] == "Codex"
    assert snapshot["top_cpu_processes"][0]["name"] == "Codex"
    assert "command_line" not in str(snapshot)
    assert monitor.current()["status"] == "available"


def test_non_mac_fail_closed():
    with patch("integrations.mac_resources.platform.system", return_value="Linux"):
        assert MacResourceMonitor(command=fake).collect() == unavailable_frame()


def test_missing_ram_and_stale_fail_closed():
    def missing(args):
        if args[-1] == "hw.memsize":
            raise OSError("secret")
        return fake(args)

    with patch("integrations.mac_resources.platform.system", return_value="Darwin"):
        monitor = MacResourceMonitor(command=missing)
        assert monitor.collect()["status"] == "unavailable"
        good = MacResourceMonitor(command=fake)
        good.collect()
        good.sampled_at -= 60
        assert good.current()["cpu_pct"] is None


def test_sustained_warning_and_recovery():
    def hot(args):
        if "top" in args[0]:
            return "CPU usage: 97.0% user, 2.0% sys, 1.0% idle"
        return fake(args)

    with patch("integrations.mac_resources.platform.system", return_value="Darwin"):
        monitor = MacResourceMonitor(command=hot)
        assert [monitor.collect()["alert"] for _ in range(3)] == ["normal", "normal", "warning"]
        monitor.command = fake
        assert [monitor.collect()["alert"] for _ in range(3)] == ["warning", "warning", "normal"]


def test_critical_pressure_immediate():
    def critical(args):
        if args[-1] == "kern.memorystatus_vm_pressure_level":
            return "4"
        return fake(args)

    with patch("integrations.mac_resources.platform.system", return_value="Darwin"):
        assert MacResourceMonitor(command=critical).collect()["alert"] == "critical"


def test_vm_missing_field_does_not_invent_usage():
    assert _vm_gib("no fields", 16 * 1024**3) is None
    assert _cpu_pct("broken") is None
    assert _swap_gib("broken") is None


def test_latest_cpu_interval_and_no_warning_from_static_swap_or_memory_usage():
    assert _cpu_pct(TOP + "CPU usage: 2.0% user, 3.0% sys, 95.0% idle") == 5

    def cached(args):
        if args[-1] == "vm.swapusage":
            return "used = 12000.00M"
        if "vm_stat" in args[0]:
            return VM.replace("330000", "1000000")
        return fake(args)

    with patch("integrations.mac_resources.platform.system", return_value="Darwin"):
        monitor = MacResourceMonitor(command=cached)
        for _ in range(4):
            assert monitor.collect()["alert"] == "normal"


def test_swap_growth_requires_observation_window_and_reports_reason():
    current = {"time": 0, "swap": 0}

    def growing(args):
        if args[-1] == "vm.swapusage":
            return f"used = {current['swap']}G"
        return fake(args)

    with (
        patch("integrations.mac_resources.platform.system", return_value="Darwin"),
        patch("integrations.mac_resources.monotonic", side_effect=lambda: current["time"]),
    ):
        monitor = MacResourceMonitor(command=growing)
        for n in range(5):
            current.update(time=n * 15, swap=n * 0.2)
            result = monitor.collect()
            if n < 2:
                assert result["swap_growth_gb"] is None
        assert result["alert"] == "warning"
        assert result["reasons"] == ["swap_growth"]


def test_failed_sample_breaks_consecutive_warning_streak():
    def hot(args):
        if "top" in args[0]:
            return "CPU usage: 99.0% user, 0.0% sys, 1.0% idle"
        return fake(args)

    with patch("integrations.mac_resources.platform.system", return_value="Darwin"):
        monitor = MacResourceMonitor(command=hot)
        monitor.collect()
        monitor.collect()
        monitor.command = lambda args: ""
        assert monitor.collect()["status"] == "unavailable"
        monitor.command = hot
        assert monitor.collect()["alert"] == "normal"


def test_thermal_helper_critical_reason_and_untrusted_output(tmp_path):
    helper = tmp_path / "thermal"
    helper.write_text("test helper fixture")
    helper.chmod(0o700)

    def command(args):
        return "critical" if args == [str(helper)] else fake(args)

    with patch("integrations.mac_resources.platform.system", return_value="Darwin"):
        monitor = MacResourceMonitor(command=command, thermal_helper=str(helper))
        result = monitor.collect()
        assert result["alert"] == "critical"
        assert result["reasons"] == ["thermal_pressure"]
        monitor.command = lambda args: "85C" if args == [str(helper)] else fake(args)
        assert monitor.collect()["thermal"] == "unknown"
