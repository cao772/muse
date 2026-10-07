import asyncio
import base64
import hashlib
import json
import struct

import pytest

from integrations.tts import MacSayTTS, MockTTS, decode_playback_wav, encode_wav, limit_output
from scripts.play_audio import upload


def test_mock_tts_is_valid_local_playback_format():
    wav = asyncio.run(MockTTS().synthesize("测试"))
    assert decode_playback_wav(wav) == b"\0\0" * 16000


@pytest.mark.parametrize(
    "data",
    [
        b"bad",
        encode_wav(b""),
        encode_wav(b"\0\0" * 80001),
        encode_wav(b"\0\0")[:-1],
        b"x" * 1048577,
    ],
)
def test_playback_rejects_malformed_or_unbounded_wav(data):
    with pytest.raises(ValueError):
        decode_playback_wav(data)


def test_limiter_caps_full_scale_and_fades_boundaries():
    raw = struct.pack("<200h", *([32767, -32768] * 100))
    output = struct.unpack("<200h", limit_output(raw))
    assert max(abs(value) for value in output) <= 16384
    assert output[0] == output[-1] == 0
    assert output[90] > 0 and output[91] < 0


class FakeSpeaker:
    def __init__(self, failure=None):
        self.pending = bytearray()
        self.pcm = bytearray()
        self.failure = failure
        self.messages = []

    @property
    def in_waiting(self):
        return len(self.pending)

    def read(self, count):
        result = bytes(self.pending[:count])
        del self.pending[:count]
        return result

    def flush(self):
        pass

    def write(self, raw):
        message = json.loads(raw)
        self.messages.append(message)
        if "play_begin" in message:
            self.expected = message["play_begin"]
            self.digest = message["sha256"]
            self.volume = message["volume"]
            self.pending += (
                f"partial console line\n\nMUSE_SPK_READY bytes={self.expected}\n".encode()
            )
        elif "play_data" in message:
            assert message["play_data"] == len(self.pcm)
            chunk = base64.b64decode(message["data"])
            assert len(chunk) <= 768
            self.pcm.extend(chunk)
            if self.failure == "reject":
                self.pending += b"MUSE_SPK_ERROR code=chunk\n"
            else:
                self.pending += f"MUSE_SPK_ACK offset={len(self.pcm)}\n".encode()
        elif "play_end" in message:
            assert self.digest == hashlib.sha256(self.pcm).hexdigest()
            size = self.expected + (2 if self.failure == "length" else 0)
            # Both status frames can arrive in the same USB read.
            self.pending += (
                f"MUSE_SPK_PLAYING volume={self.volume}\n"
                f"MUSE_SPK_DONE bytes={size} frames={size // 2} elapsed_ms=1000\n"
            ).encode()


def test_upload_round_trip_and_batched_completion():
    pcm = b"\x01\x00" * 1000
    speaker = FakeSpeaker()
    result = upload(speaker, pcm)
    assert speaker.pcm == pcm
    assert result == {"bytes": 2000, "frames": 1000, "elapsed_ms": 1000}


@pytest.mark.parametrize("failure", ["reject", "length"])
def test_upload_error_cancels_without_returning_success(failure):
    speaker = FakeSpeaker(failure)
    with pytest.raises(ValueError):
        upload(speaker, b"\0\0" * 1000)
    assert speaker.messages[-1] == {"play_cancel": True}


@pytest.mark.parametrize("pcm", [b"", b"\0", b"\0" * 160002])
def test_upload_checks_bounds_before_usb_write(pcm):
    speaker = FakeSpeaker()
    with pytest.raises(ValueError):
        upload(speaker, pcm)
    assert not speaker.messages


def test_mac_tts_stdin_and_private_temp_cleanup(monkeypatch):
    from pathlib import Path

    import integrations.tts as tts

    calls = []
    directories = []

    def run(command, **options):
        calls.append(command)
        assert options["capture_output"] and options["timeout"] == 20
        if command[0] == "/usr/bin/say":
            assert options["input"] == "测试短句".encode()
            assert "测试短句" not in command
            directory = Path(command[-1]).parent
            assert directory.stat().st_mode & 0o777 == 0o700
            directories.append(directory)
        else:
            Path(command[-1]).write_bytes(encode_wav(b"\0\0" * 16000))

    monkeypatch.setattr(tts.sys, "platform", "darwin")
    monkeypatch.setattr(tts.subprocess, "run", run)
    data = asyncio.run(MacSayTTS().synthesize("测试短句"))
    assert len(decode_playback_wav(data)) == 32000
    assert len(calls) == 2
    assert not directories[0].exists()


def test_upload_bounded_volume_is_sent_and_confirmed():
    speaker = FakeSpeaker()
    assert upload(speaker, b"\0\0" * 1000, volume=50)["bytes"] == 2000
    assert speaker.messages[0]["volume"] == 50


@pytest.mark.parametrize("volume", [0, 9, 81, 100, True, 20.5])
def test_upload_volume_rejected_before_writing(volume):
    speaker = FakeSpeaker()
    with pytest.raises(ValueError):
        upload(speaker, b"\0\0", volume=volume)
    assert not speaker.messages
