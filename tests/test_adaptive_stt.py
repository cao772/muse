import struct

import pytest

from gateway.talk import input_wav
from integrations.stt import stereo_wav_to_mono


def test_twenty_second_stt_input_is_supported_without_changing_tts_bounds():
    pcm = struct.pack("<hh", 1000, 3000) * 320000
    audio = stereo_wav_to_mono(input_wav(pcm))
    assert audio.seconds == 20 and len(audio.pcm) == 640000


def test_more_than_twenty_seconds_is_rejected():
    with pytest.raises(ValueError):
        stereo_wav_to_mono(input_wav(b"\0" * (320001 * 4)))
