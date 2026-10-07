"""Run in the isolated MLX environment; stdin request, private WAV output."""

import json
import math
import os
import sys

from integrations.local_tts import CANDIDATES, MODEL, REVISION
from integrations.tts import (
    MAX_FRAMES,
    RATE,
    TTSOutputTooLong,
    decode_playback_wav,
    encode_wav,
    limit_output,
)


def main():
    import mlx.core as mx
    import numpy as np
    from huggingface_hub import snapshot_download
    from mlx_audio.tts.utils import load_model
    from scipy.signal import resample_poly

    request = json.loads(sys.stdin.buffer.read(4096))
    text, voice = request["text"], request["voice"]
    if voice not in CANDIDATES or not text.strip() or len(text) > 80 or "\0" in text:
        raise ValueError("Invalid offline TTS request")
    local = snapshot_download(MODEL, revision=REVISION, local_files_only=True)
    model = load_model(local)
    mx.random.seed(0)
    results = list(
        model.generate_custom_voice(
            text=text,
            speaker=voice,
            language="Chinese",
            max_tokens=128,
            verbose=False,
        )
    )
    if len(results) != 1 or results[0].token_count >= 128:
        raise ValueError("Incomplete offline TTS output")
    result = results[0]
    audio = np.asarray(result.audio, dtype=np.float32)
    if audio.ndim != 1 or not np.isfinite(audio).all() or not len(audio):
        raise ValueError("Offline TTS output exceeds bound")
    if len(audio) > result.sample_rate * 5:
        raise TTSOutputTooLong("Offline TTS output exceeds bound")
    # Qwen emits 24kHz float mono; polyphase low-pass resampling preserves pitch.
    divisor = math.gcd(RATE, result.sample_rate)
    audio = resample_poly(audio, RATE // divisor, result.sample_rate // divisor)
    if not 0 < len(audio) <= MAX_FRAMES:
        raise TTSOutputTooLong("Resampled output exceeds bound")
    pcm = np.rint(np.clip(audio, -1, 32767 / 32768) * 32768).astype("<i2").tobytes()
    wav = encode_wav(limit_output(pcm))
    decode_playback_wav(wav)
    with os.fdopen(
        os.open(request["output"], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb"
    ) as output:
        output.write(wav)


if __name__ == "__main__":
    try:
        main()
    except TTSOutputTooLong:
        raise SystemExit(2) from None
