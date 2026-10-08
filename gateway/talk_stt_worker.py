"""Private stdin WAV → local Whisper → stdout JSON, in a killable process."""

import json
import sys

from integrations.stt import MLXWhisperSTT, stereo_wav_to_mono


def main():
    if "--resident" in sys.argv:
        import base64
        import importlib

        import mlx.core as mx

        from integrations.model_worker import run

        def load():
            module = importlib.import_module("mlx_whisper.transcribe")
            module.ModelHolder.get_model(sys.argv[1], mx.float16)
            from integrations.stt import MonoAudio

            model = MLXWhisperSTT(sys.argv[1])
            try:
                model._transcribe(MonoAudio(b"\0\0" * 16000))
            except RuntimeError:
                pass  # Silence is only kernel warm-up, never sent to the LLM.
            return model

        run(
            load,
            lambda model, request: {
                "text": model._transcribe(
                    stereo_wav_to_mono(base64.b64decode(request["wav"], validate=True))
                )
            },
        )
        return
    data = sys.stdin.buffer.read(2097153)
    audio = stereo_wav_to_mono(data)
    text = MLXWhisperSTT(sys.argv[1])._transcribe(audio)
    print(json.dumps({"text": text}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
