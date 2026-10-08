"""Bounded Stage 3 WAV input; local transcription, no audio upload."""

import asyncio
import io
import sys
import threading
import wave
from array import array
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class MonoAudio:
    pcm: bytes
    rate: int = 16000

    @property
    def seconds(self) -> float:
        return len(self.pcm) / (2 * self.rate)


def stereo_wav_to_mono(data: bytes) -> MonoAudio:
    if len(data) > 2097152:
        raise ValueError("WAV exceeds 2MiB input limit")
    try:
        with wave.open(io.BytesIO(data), "rb") as source:
            if (
                source.getnchannels() != 2
                or source.getsampwidth() != 2
                or source.getframerate() != 16000
                or source.getcomptype() != "NONE"
                or not 1 <= source.getnframes() <= 320000
            ):
                raise ValueError("Expected 16kHz/16bit/stereo PCM WAV, at most 20 seconds")
            frames = source.getnframes()
            raw = source.readframes(frames)
            if len(raw) != frames * 4:
                raise ValueError("Truncated WAV")
    except (wave.Error, EOFError):
        raise ValueError("Invalid PCM WAV") from None
    stereo = array("h", raw)
    if sys.byteorder != "little":
        stereo.byteswap()
    # Widen to Python integers before averaging to avoid int16 overflow.
    mono = array(
        "h", ((int(stereo[i]) + int(stereo[i + 1])) // 2 for i in range(0, len(stereo), 2))
    )
    if sys.byteorder != "little":
        mono.byteswap()
    return MonoAudio(mono.tobytes())


class STTAdapter(Protocol):
    async def transcribe(self, audio: MonoAudio) -> str: ...


class MockSTT:
    def __init__(self, text: str = "[mock STT] 测试文本"):
        self.text = text

    async def transcribe(self, audio: MonoAudio) -> str:
        return self.text


class MLXWhisperSTT:
    _lock = threading.Lock()

    def __init__(self, model: str):
        self.model = model

    def _transcribe(self, audio: MonoAudio) -> str:
        try:
            import mlx_whisper
            import numpy as np
        except ImportError:
            raise RuntimeError("Local STT requires Apple Silicon and uv sync --extra stt") from None
        samples = np.frombuffer(audio.pcm, dtype="<i2").astype(np.float32) / 32768.0
        with self._lock:
            result = mlx_whisper.transcribe(
                samples,
                path_or_hf_repo=self.model,
                language="zh",
                task="transcribe",
                temperature=0.0,
                verbose=None,
                condition_on_previous_text=False,
            )
        text = result.get("text", "").strip()
        if not text:
            raise RuntimeError("No speech recognized")
        return text

    async def transcribe(self, audio: MonoAudio) -> str:
        return await asyncio.to_thread(self._transcribe, audio)


def create_stt(name: str, model: str) -> STTAdapter:
    if name == "mock":
        return MockSTT()
    if name == "mlx-whisper":
        return MLXWhisperSTT(model)
    raise ValueError("Unsupported STT adapter")
