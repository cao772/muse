"""Report stereo WAV channel statistics without logging or uploading audio samples."""

import argparse
import array
import json
import math
import sys
import wave
from pathlib import Path


def analyze(path: Path):
    with wave.open(str(path), "rb") as recording:
        if recording.getnchannels() != 2 or recording.getsampwidth() != 2:
            raise ValueError("Expected 16-bit stereo PCM WAV")
        rate, frames = recording.getframerate(), recording.getnframes()
        if not 1 <= frames <= 16000 * 5 or rate != 16000:
            raise ValueError("Expected at most 5 seconds at 16000 Hz")
        pcm = array.array("h", recording.readframes(frames))
        if len(pcm) != frames * 2:
            raise ValueError("Truncated WAV")
        if sys.byteorder != "little":
            pcm.byteswap()
    channels = [pcm[0::2], pcm[1::2]]
    result = {"rate": rate, "bits": 16, "channels": 2, "frames": frames, "seconds": frames / rate}
    for name, values in zip(["L", "R"], channels, strict=True):
        rms = math.sqrt(sum(value * value for value in values) / frames)
        result[name] = {
            "peak": max(abs(value) for value in values),
            "rms": round(rms, 2),
            "rms_dbfs": round(20 * math.log10(rms / 32768), 2) if rms else -96,
            "clipped_samples": sum(value in (-32768, 32767) for value in values),
            "mean": round(sum(values) / frames, 2),
        }
    result["equal_samples_fraction"] = sum(a == b for a, b in zip(*channels, strict=True)) / frames
    means = [sum(values) / frames for values in channels]
    energies = [sum((v - means[ch]) ** 2 for v in values) for ch, values in enumerate(channels)]
    covariance = sum((a - means[0]) * (b - means[1]) for a, b in zip(*channels, strict=True))
    result["correlation"] = (
        round(covariance / math.sqrt(energies[0] * energies[1]), 4) if all(energies) else None
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wav", type=Path)
    args = parser.parse_args()
    print(json.dumps(analyze(args.wav), ensure_ascii=False, indent=2))
