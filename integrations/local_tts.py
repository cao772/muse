"""Isolated, offline MLX Qwen3-TTS adapter for Apple Silicon."""

import asyncio
import json
import os
import subprocess
import tempfile
from pathlib import Path

from integrations.tts import decode_playback_wav

MODEL = "mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit"
REVISION = "049ef77fe8816b536193c0c25f9a214d17921282"
CANDIDATES = ("Serena", "Vivian", "Sohee")
RUNTIME = Path.home() / ".cache/muse-toolchains/tts/bin/python"


class LocalQwenTTS:
    def __init__(self, voice="Serena", python=RUNTIME):
        if voice not in CANDIDATES:
            raise ValueError("Choose Serena, Vivian or Sohee")
        self.voice, self.python = voice, Path(python)

    def _synthesize(self, text):
        if not text.strip() or len(text) > 80 or "\0" in text:
            raise ValueError("TTS requires 1–80 characters without NUL")
        if not self.python.is_file():
            raise RuntimeError("Install the isolated local TTS runtime; see docs/tts-offline.md")
        try:
            with tempfile.TemporaryDirectory(prefix="muse-local-tts-") as directory:
                path = Path(directory) / "speech.wav"
                env = os.environ.copy()
                env.update(
                    HF_HUB_OFFLINE="1",
                    TRANSFORMERS_OFFLINE="1",
                    HF_HUB_DISABLE_TELEMETRY="1",
                    DO_NOT_TRACK="1",
                )
                subprocess.run(
                    [str(self.python), "-m", "integrations.local_tts_worker"],
                    cwd=Path(__file__).resolve().parents[1],
                    input=json.dumps(
                        {"text": text, "voice": self.voice, "output": str(path)}
                    ).encode(),
                    capture_output=True,
                    check=True,
                    timeout=180,
                    env=env,
                )
                data = path.read_bytes()
                decode_playback_wav(data)
                return data
        except (OSError, subprocess.SubprocessError, ValueError):
            raise RuntimeError(
                "Offline TTS failed; check cached model/runtime and 5-second output limit"
            ) from None

    async def synthesize(self, text):
        return await asyncio.to_thread(self._synthesize, text)
