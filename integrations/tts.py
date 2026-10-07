"""Bounded local macOS TTS; never sends text or audio to a cloud service."""

import asyncio
import io
import subprocess
import sys
import tempfile
import wave
from array import array
from pathlib import Path
from typing import Protocol

RATE = 16000
MAX_FRAMES = RATE * 5


def decode_playback_wav(data: bytes) -> bytes:
    if len(data) > 1048576:
        raise ValueError("Playback WAV exceeds 1MiB")
    try:
        with wave.open(io.BytesIO(data), "rb") as source:
            if (
                source.getnchannels() != 1
                or source.getsampwidth() != 2
                or source.getframerate() != RATE
                or source.getcomptype() != "NONE"
                or not 1 <= source.getnframes() <= MAX_FRAMES
            ):
                raise ValueError("Playback requires 16kHz/16bit/mono PCM WAV, at most 5 seconds")
            frames = source.getnframes()
            pcm = source.readframes(frames)
            if len(pcm) != frames * 2:
                raise ValueError("Truncated playback WAV")
            return pcm
    except (wave.Error, EOFError):
        raise ValueError("Invalid playback WAV") from None


def encode_wav(pcm: bytes) -> bytes:
    stream = io.BytesIO()
    with wave.open(stream, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(RATE)
        output.writeframes(pcm)
    return stream.getvalue()


def limit_output(pcm: bytes) -> bytes:
    samples = array("h", pcm)
    if sys.byteorder != "little":
        samples.byteswap()
    peak = max((abs(v) for v in samples), default=0)
    gain = min(1.0, 16384 / peak) if peak else 1.0
    # Cap to -6dBFS and fade the first/last 5ms to reduce boundary clicks.
    fade = min(80, len(samples) // 2)
    for i, value in enumerate(samples):
        envelope = min(1.0, i / fade, (len(samples) - 1 - i) / fade) if fade else 1.0
        samples[i] = round(value * gain * envelope)
    if sys.byteorder != "little":
        samples.byteswap()
    return samples.tobytes()


class TTSAdapter(Protocol):
    async def synthesize(self, text: str) -> bytes: ...


class MockTTS:
    async def synthesize(self, text: str) -> bytes:
        return encode_wav(b"\0\0" * RATE)


class MacSayTTS:
    def __init__(self, voice: str = "Tingting"):
        self.voice = voice

    def _synthesize(self, text: str) -> bytes:
        if sys.platform != "darwin":
            raise RuntimeError("macOS say TTS requires macOS")
        if not text.strip() or len(text) > 80 or "\0" in text:
            raise ValueError("TTS requires 1–80 characters without NUL")
        try:
            with tempfile.TemporaryDirectory(prefix="muse-tts-") as directory:
                folder = Path(directory)
                source, converted = folder / "speech.aiff", folder / "speech.wav"
                # Text is stdin, never a shell command or process-list argument.
                subprocess.run(
                    ["/usr/bin/say", "-v", self.voice, "-r", "180", "-f", "-", "-o", str(source)],
                    input=text.encode(),
                    capture_output=True,
                    check=True,
                    timeout=20,
                )
                subprocess.run(
                    [
                        "/usr/bin/afconvert",
                        "-f",
                        "WAVE",
                        "-d",
                        "LEI16@16000",
                        "-c",
                        "1",
                        str(source),
                        str(converted),
                    ],
                    capture_output=True,
                    check=True,
                    timeout=20,
                )
                data = converted.read_bytes()
                pcm = decode_playback_wav(data)
                return encode_wav(limit_output(pcm))
        except (OSError, subprocess.SubprocessError):
            raise RuntimeError(
                "Local TTS failed; check installed voice and macOS audio tools"
            ) from None

    async def synthesize(self, text: str) -> bytes:
        return await asyncio.to_thread(self._synthesize, text)
