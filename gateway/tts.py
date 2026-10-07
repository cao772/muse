"""Generate a short, private playback WAV from a fixed local Chinese sentence."""

import argparse
import asyncio
import os
from datetime import datetime
from pathlib import Path
from time import perf_counter

from integrations.tts import MacSayTTS, decode_playback_wav

RECORDINGS = Path(__file__).resolve().parents[1] / "recordings"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", default="你好，我是 Muse，扬声器测试。")
    parser.add_argument("--voice", default="Tingting")
    args = parser.parse_args()
    started = perf_counter()
    try:
        data = asyncio.run(MacSayTTS(args.voice).synthesize(args.text))
        pcm = decode_playback_wav(data)
        directory = RECORDINGS / "tts"
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        RECORDINGS.chmod(0o700)
        directory.chmod(0o700)
        path = directory / ("muse-tts-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".wav")
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as stream:
            stream.write(data)
    except (ValueError, RuntimeError, OSError):
        raise SystemExit("TTS failed; check voice, text length and 5-second output limit") from None
    print(
        f"PASS: local TTS, {len(pcm) / 32000:.3f}s, 16kHz mono s16le, "
        f"elapsed {perf_counter() - started:.3f}s; WAV: {path}"
    )


if __name__ == "__main__":
    main()
