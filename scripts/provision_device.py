"""Send local Wi-Fi configuration over USB and verify Stage 1 heartbeat markers."""

import argparse
import json
import re
import time
from pathlib import Path
from urllib.parse import urlsplit

import serial
from dotenv import dotenv_values


def configuration(path: Path) -> dict[str, str]:
    values = dotenv_values(path)
    keys = {
        "ssid": "MUSE_WIFI_SSID",
        "password": "MUSE_WIFI_PASSWORD",
        "uri": "MUSE_GATEWAY_URI",
        "device_id": "MUSE_DEVICE_ID",
        "token": "MUSE_DEVICE_TOKEN",
    }
    config = {key: values.get(env) or "" for key, env in keys.items()}
    if not 1 <= len(config["ssid"].encode()) <= 32:
        raise ValueError("Fill MUSE_WIFI_SSID in the local configuration file")
    if len(config["password"].encode()) > 64:
        raise ValueError("Wi-Fi password exceeds 64 bytes")
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", config["device_id"]):
        raise ValueError("Invalid device ID")
    token = config["token"]
    if not 32 <= len(token) <= 128 or not token.isascii() or any(c.isspace() for c in token):
        raise ValueError("Invalid device token")
    uri = urlsplit(config["uri"])
    if uri.scheme != "ws" or not uri.hostname or uri.path != "/ws" or uri.username or uri.password:
        raise ValueError("Stage 1 requires a trusted-LAN ws://Mac-IP:port/ws URI")
    payload = json.dumps(config, ensure_ascii=False).encode() + b"\n"
    if len(payload) >= 768:
        raise ValueError("Configuration exceeds firmware input size")
    return config


def provision(port: str, path: Path, timeout: float):
    config = configuration(path)
    markers = set()
    pongs = set()
    sent = False
    deadline = time.monotonic() + timeout
    with serial.Serial(port, 115200, timeout=0.5) as device:
        while time.monotonic() < deadline:
            line = device.readline().decode(errors="replace")
            if "MUSE_CONFIG_READY" in line and not sent:
                device.write(json.dumps(config, ensure_ascii=False).encode() + b"\n")
                device.flush()
                sent = True
                print("Configuration sent over USB (values hidden)", flush=True)
            for marker in [
                "MUSE_CONFIG_OK",
                "MUSE_CONFIG_INVALID",
                "WIFI_GOT_IP",
                "WS_CONNECTED",
                "HELLO_OK",
                "PONG_TIMEOUT",
                "WS_DISCONNECTED",
                "WIFI_DISCONNECTED",
            ]:
                if marker in line:
                    print(marker, flush=True)
                    markers.add(marker)
            match = re.search(r"PONG_OK id=(p-\d+)", line)
            if match:
                pongs.add(match[1])
                print(f"PONG_OK {match[1]}", flush=True)
            if {"WIFI_GOT_IP", "HELLO_OK"} <= markers and len(pongs) >= 3:
                print(
                    "PASS: hardware Wi-Fi → authenticated WebSocket → hello → 3 ping/pong",
                    flush=True,
                )
                return
    raise SystemExit(
        "Stage 1 did not complete before timeout; check Wi-Fi, gateway, and device state"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--config", type=Path, default=Path(".env.device"))
    parser.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args()
    try:
        provision(args.port, args.config, args.timeout)
    except (ValueError, OSError, serial.SerialException) as error:
        raise SystemExit(str(error)) from error
