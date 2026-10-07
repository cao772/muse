"""Local, one-shot WAV → STT → optional LLM. No new network audio endpoint."""

import argparse
import asyncio
import json
from pathlib import Path
from time import perf_counter

from gateway.config import Settings
from integrations.llm import TextProvider, create_provider
from integrations.stt import STTAdapter, create_stt, stereo_wav_to_mono


async def process_wav(
    data: bytes,
    stt: STTAdapter,
    provider: TextProvider | None = None,
    provider_timeout: float = 15,
) -> dict:
    audio = stereo_wav_to_mono(data)
    started = perf_counter()
    text = await stt.transcribe(audio)
    stt_seconds = perf_counter() - started
    answer = None
    llm_seconds = None
    if provider is not None:
        started = perf_counter()
        answer = await asyncio.wait_for(provider.reply(text), timeout=provider_timeout)
        llm_seconds = perf_counter() - started
    return {
        "audio_seconds": audio.seconds,
        "transcript": text,
        "reply": answer,
        "stt_seconds": round(stt_seconds, 3),
        "llm_seconds": round(llm_seconds, 3) if llm_seconds is not None else None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wav", type=Path)
    parser.add_argument("--reply", action="store_true", help="Send transcript to configured LLM")
    args = parser.parse_args()
    settings = Settings()
    try:
        with args.wav.open("rb") as stream:
            data = stream.read(1048577)
        result = asyncio.run(
            process_wav(
                data,
                create_stt(settings.stt_provider, settings.stt_model),
                create_provider(settings.provider, settings) if args.reply else None,
                settings.provider_timeout_seconds,
            )
        )
    except Exception:
        # Model/download/API exceptions may contain headers or private paths.
        raise SystemExit(
            "Voice processing failed; check WAV format, local model and configuration"
        ) from None
    result.update(
        stt=settings.stt_provider,
        stt_model=settings.stt_model,
        provider=settings.provider if args.reply else None,
        llm_model=settings.llm_model if args.reply else None,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
