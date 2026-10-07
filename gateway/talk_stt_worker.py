"""Private stdin WAV → local Whisper → stdout JSON, in a killable process."""

import json
import sys

from integrations.stt import MLXWhisperSTT, stereo_wav_to_mono


def main():
    data = sys.stdin.buffer.read(1048577)
    audio = stereo_wav_to_mono(data)
    text = MLXWhisperSTT(sys.argv[1])._transcribe(audio)
    print(json.dumps({"text": text}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
