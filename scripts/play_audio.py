"""Upload at most 5s mono PCM over physical USB; device verifies SHA-256 before playback."""

import argparse
import base64
import hashlib
import json
import re
import time
from pathlib import Path

import serial

from integrations.tts import decode_playback_wav


def wait_for(device, pattern: str, seconds: float = 5) -> re.Match:
    deadline = time.monotonic() + seconds
    buffered = bytearray(getattr(device, "_muse_pending", b""))
    device._muse_pending = b""
    while time.monotonic() < deadline:
        if b"\n" not in buffered:
            buffered.extend(device.read(min(device.in_waiting or 1, 4096)))
            if len(buffered) > 8192:
                raise ValueError("USB response exceeds bound")
            continue
        raw, _, rest = buffered.partition(b"\n")
        buffered = bytearray(rest)
        line = raw.decode(errors="replace").strip()
        error = re.fullmatch(r"MUSE_SPK_ERROR code=([a-z_]{1,24})", line)
        if error:
            raise ValueError(f"Device rejected playback ({error[1]})")
        match = re.fullmatch(pattern, line)
        if match:
            # Retain any already-read status frame for the next wait.
            device._muse_pending = bytes(buffered)
            return match
    raise ValueError(f"Playback response timed out: expected {pattern}")


def upload(device, pcm: bytes, volume: int = 80, on_playing=None) -> dict:
    if not isinstance(volume, int) or isinstance(volume, bool) or not 10 <= volume <= 80:
        raise ValueError("Playback volume must be an integer between 10 and 80")
    if not pcm or len(pcm) > 160000 or len(pcm) % 2:
        raise ValueError("Playback requires 1–80000 mono int16 frames")

    def send(message):
        device.write(json.dumps(message, separators=(",", ":")).encode() + b"\n")
        device.flush()

    def wait(pattern, seconds=5):
        return wait_for(device, pattern, seconds)

    try:
        send(
            {
                "play_begin": len(pcm),
                "sha256": hashlib.sha256(pcm).hexdigest(),
                "rate": 16000,
                "channels": 1,
                "bits": 16,
                "volume": volume,
            }
        )
        wait(f"MUSE_SPK_READY bytes={len(pcm)}")
        for offset in range(0, len(pcm), 768):
            chunk = pcm[offset : offset + 768]
            send({"play_data": offset, "data": base64.b64encode(chunk).decode()})
            wait(f"MUSE_SPK_ACK offset={offset + len(chunk)}")
        send({"play_end": True})
        wait(f"MUSE_SPK_PLAYING volume={volume}")
        if on_playing:
            on_playing()
        done = wait(r"MUSE_SPK_DONE bytes=(\d+) frames=(\d+) elapsed_ms=(\d+)", 8)
        if int(done[1]) != len(pcm) or int(done[2]) != len(pcm) // 2:
            raise ValueError("Playback completion length mismatch")
        return {"bytes": int(done[1]), "frames": int(done[2]), "elapsed_ms": int(done[3])}
    except Exception:
        try:
            send({"play_cancel": True})
        except Exception:
            pass
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wav", type=Path)
    parser.add_argument("--port", required=True)
    parser.add_argument("--volume", type=int, choices=range(10, 81), default=80)
    args = parser.parse_args()
    try:
        with args.wav.open("rb") as stream:
            pcm = decode_playback_wav(stream.read(1048577))
        with serial.Serial(args.port, 115200, timeout=0.2, write_timeout=5) as device:
            device.reset_input_buffer()
            result = upload(device, pcm, args.volume)
    except ValueError as error:
        raise SystemExit(f"USB playback failed: {error}") from None
    except (OSError, serial.SerialException):
        raise SystemExit("USB playback failed; check exclusive serial access") from None
    print(
        "PASS: bounded USB upload, SHA-256 verified by device, codec write completed; "
        + json.dumps(result)
    )
    print("Audible clarity still requires human confirmation.")


if __name__ == "__main__":
    main()
