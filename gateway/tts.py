"""Generate a short, private playback WAV from a fixed local Chinese sentence."""

import argparse
import asyncio
import os
import re
from datetime import datetime
from pathlib import Path
from time import perf_counter

from integrations.local_tts import CANDIDATES, MODEL, LocalQwenTTS
from integrations.tts import MacSayTTS, decode_playback_wav

RECORDINGS = Path(__file__).resolve().parents[1] / "recordings"


def save_wav(data, label):
    label = re.sub(r"[^a-zA-Z0-9_.-]", "_", label)
    pcm = decode_playback_wav(data)
    directory = RECORDINGS / "tts"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    RECORDINGS.chmod(0o700)
    directory.chmod(0o700)
    path = directory / (label + "-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".wav")
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as stream:
        stream.write(data)
    return path, len(pcm) / 32000


async def generate(args):
    voices = (
        CANDIDATES
        if args.audition
        else (args.voice or (CANDIDATES[0] if args.provider == "qwen-local" else "Tingting"),)
    )
    if args.audition and args.provider != "qwen-local":
        raise ValueError("--audition requires --provider qwen-local")
    text = args.text or (
        "你好，我是 Muse，有什么可以帮你的吗？"
        if args.audition
        else "你好，我是 Muse，扬声器测试。"
    )
    for index, voice in enumerate(voices, 1):
        adapter = LocalQwenTTS(voice) if args.provider == "qwen-local" else MacSayTTS(voice)
        started = perf_counter()
        data = await adapter.synthesize(text)
        path, duration = save_wav(data, f"muse-{args.provider}-{voice}")
        model = MODEL if args.provider == "qwen-local" else "macOS-say"
        print(
            f"{index}. provider={args.provider} model={model} voice={voice} "
            f"duration={duration:.3f}s elapsed={perf_counter() - started:.3f}s WAV: {path}",
            flush=True,
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text")
    parser.add_argument("--voice")
    parser.add_argument("--provider", choices=("mac-say", "qwen-local"), default="mac-say")
    parser.add_argument("--audition", action="store_true", help="Generate three Qwen candidates")
    args = parser.parse_args()
    try:
        asyncio.run(generate(args))
    except (ValueError, RuntimeError, OSError) as error:
        raise SystemExit(f"TTS failed: {error}") from None


if __name__ == "__main__":
    main()
