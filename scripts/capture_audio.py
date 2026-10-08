"""Receive bounded stereo PCM over USB; verify framing/hash before saving a private WAV."""

import argparse
import base64
import hashlib
import json
import os
import re
import time
import wave
from datetime import datetime
from pathlib import Path

import serial

RATE = 16000
RECORDINGS = Path(__file__).resolve().parents[1] / "recordings"


class PCMTransfer:
    def __init__(self, seconds: int, *, variable: bool = False):
        if seconds not in range(1, 21 if variable else 6):
            raise ValueError("Recording duration outside allowed capture bounds")
        self.maximum = seconds * RATE * 4
        self.variable = variable
        self.expected = self.maximum
        self.pcm = bytearray()
        self.digest = None

    def feed(self, line: str) -> bool:
        if line.startswith("MUSE_PCM_BEGIN "):
            match = re.fullmatch(
                r"MUSE_PCM_BEGIN rate=16000 channels=2 bits=16 bytes=(\d+) sha256=([a-f0-9]{64})",
                line,
            )
            if (
                not match
                or self.digest is not None
                or not 0 < int(match[1]) <= self.maximum
                or int(match[1]) % 4
                or (not self.variable and int(match[1]) != self.expected)
            ):
                raise ValueError("Unexpected audio format or length")
            self.expected = int(match[1])
            self.digest = match[2]
        elif line.startswith("MUSE_PCM_DATA "):
            match = re.fullmatch(r"MUSE_PCM_DATA offset=(\d+) data=([A-Za-z0-9+/=]+)", line)
            if not match:
                raise ValueError(f"Malformed audio frame after {len(self.pcm)} PCM bytes")
            if not self.digest or int(match[1]) != len(self.pcm):
                raise ValueError(
                    f"Audio offset mismatch: expected {len(self.pcm)}, received {match[1]}"
                )
            chunk = base64.b64decode(match[2], validate=True)
            if not chunk or len(chunk) > 768 or len(self.pcm) + len(chunk) > self.expected:
                raise ValueError("Audio chunk exceeds declared bounds")
            self.pcm.extend(chunk)
        elif line.startswith("MUSE_PCM_END "):
            match = re.fullmatch(r"MUSE_PCM_END bytes=(\d+) sha256=([a-f0-9]{64})", line)
            if (
                not match
                or len(self.pcm) != self.expected
                or int(match[1]) != self.expected
                or match[2] != self.digest
                or hashlib.sha256(self.pcm).hexdigest() != self.digest
            ):
                raise ValueError("Incomplete audio or SHA-256 mismatch")
            return True
        return False


class CaptureCancelled(ValueError):
    def __init__(self, reason):
        self.reason = reason
        super().__init__("Bounded capture cancelled")


class CaptureTimeout(ValueError):
    pass


def receive_pcm(device, seconds: int = 5, wait_button: bool = True) -> bytes:
    """Receive verified PCM on an already-owned USB connection, without writing a file."""
    transfer = PCMTransfer(seconds)
    if wait_button:
        if seconds != 5:
            raise ValueError("Use default screen capture bounds; fixed mode remains 5 seconds")
    else:
        device.write(json.dumps({"capture_seconds": seconds}).encode() + b"\n")
        device.flush()
    deadline = time.monotonic() + (180 if wait_button else seconds + 45)
    buffered = bytearray(getattr(device, "_muse_pending", b""))
    device._muse_pending = b""
    while time.monotonic() < deadline:
        if b"\n" not in buffered:
            buffered.extend(device.read(min(device.in_waiting or 1, 4096)))
            if len(buffered) > 8192:
                raise ValueError("USB line exceeds transport bound")
            continue
        raw, _, rest = buffered.partition(b"\n")
        buffered = bytearray(rest)
        line = raw.decode(errors="replace").strip()
        if "AUDIO_EXPORT_ERROR" in line and transfer.digest is None:
            # A prior receiver may have stopped mid-export; wait for a fresh BEGIN.
            continue
        if transfer.digest is None and line.startswith(("MUSE_PCM_DATA ", "MUSE_PCM_END ")):
            continue
        if any(
            marker in line
            for marker in ("AUDIO_CAPTURE_REJECTED", "AUDIO_ERROR", "AUDIO_EXPORT_ERROR")
        ):
            raise ValueError(
                f"Device stopped capture/export after {len(transfer.pcm)} verified PCM bytes"
            )
        if re.search(r"AUDIO_RECORDING seconds=20 mode=adaptive$", line):
            if transfer.digest is not None or transfer.pcm:
                raise ValueError("Recording mode changed during an audio transfer")
            transfer = PCMTransfer(20, variable=True)
        cancelled = re.search(r"AUDIO_CAPTURE_CANCELLED reason=(no_speech|limit)$", line)
        if cancelled:
            device._muse_pending = bytes(buffered)
            raise CaptureCancelled(cancelled[1])
        if "UI_AUDIO_RECORD_REQUEST" in line:
            device._muse_capture_started = time.monotonic()
        state = re.search(r"VOICE_STATE (Ready|Listening|Thinking|Speaking)$", line)
        if state:
            print("Device: " + state[1], flush=True)
        # Do not print PCM/base64 or arbitrary device logs.
        metadata = re.search(r"AUDIO_CAPTURED frames=\d+ elapsed_ms=\d+", line)
        if metadata:
            print(metadata.group(0), flush=True)
        if line.startswith("MUSE_PCM_BEGIN "):
            deadline = time.monotonic() + 45
        before = len(transfer.pcm)
        if transfer.feed(line):
            device._muse_pending = bytes(buffered)
            return bytes(transfer.pcm)
        if len(transfer.pcm) > before:
            device.write(json.dumps({"pcm_ack": len(transfer.pcm)}).encode() + b"\n")
            device.flush()
    else:
        raise CaptureTimeout("USB recording timed out; no WAV saved")


def capture(port: str, seconds: int, directory: Path, wait_button: bool = False) -> Path:
    if not directory.resolve().is_relative_to(RECORDINGS.resolve()):
        raise ValueError("WAV must stay under the project recordings directory (Git ignored)")
    with serial.Serial(port, 115200, timeout=0.5) as device:
        device.reset_input_buffer()
        if wait_button:
            print("Receiver ready: tap Audio Input → Speak on the board, then speak", flush=True)
        pcm = receive_pcm(device, seconds, wait_button)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    name = "muse-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".wav"
    path = directory / name
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            with wave.open(stream, "wb") as output:
                output.setnchannels(2)
                output.setsampwidth(2)
                output.setframerate(RATE)
                output.writeframes(pcm)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    print(
        f"PASS: {len(pcm) / (RATE * 4):.3f}s, 16000 Hz, stereo s16le, "
        f"SHA-256 verified; WAV: {path.resolve()}"
    )
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--seconds", type=int, choices=range(1, 6), default=5)
    parser.add_argument("--directory", type=Path, default=RECORDINGS)
    parser.add_argument(
        "--wait-button", action="store_true", help="Wait for the screen Speak button"
    )
    args = parser.parse_args()
    try:
        capture(args.port, args.seconds, args.directory, args.wait_button)
    except (ValueError, OSError, serial.SerialException) as error:
        raise SystemExit(str(error)) from error
