import base64
import hashlib
import subprocess
from pathlib import Path

import pytest

from scripts.capture_audio import PCMTransfer


@pytest.fixture
def audio_transfer():
    pcm = b"\x01\x00\x02\x00" * 16000
    digest = hashlib.sha256(pcm).hexdigest()
    begin = f"MUSE_PCM_BEGIN rate=16000 channels=2 bits=16 bytes={len(pcm)} sha256={digest}"
    end = f"MUSE_PCM_END bytes={len(pcm)} sha256={digest}"
    chunks = [
        f"MUSE_PCM_DATA offset={offset} data="
        + base64.b64encode(pcm[offset : offset + 768]).decode()
        for offset in range(0, len(pcm), 768)
    ]
    return pcm, begin, chunks, end


def test_usb_pcm_round_trip(audio_transfer):
    pcm, begin, chunks, end = audio_transfer
    transfer = PCMTransfer(1)
    assert not transfer.feed("I (10) muse: PONG_OK id=p-1")
    assert not transfer.feed(begin)
    for line in chunks:
        assert not transfer.feed(line)
    assert transfer.feed(end)
    assert bytes(transfer.pcm) == pcm


@pytest.mark.parametrize("failure", ["missing", "duplicate", "corrupt", "format", "oversize"])
def test_usb_pcm_rejects_incomplete_or_invalid_audio(audio_transfer, failure):
    _, begin, chunks, end = audio_transfer
    transfer = PCMTransfer(1)
    with pytest.raises(ValueError):
        if failure == "format":
            transfer.feed(begin.replace("channels=2", "channels=1"))
        elif failure == "oversize":
            transfer.feed(begin.replace("bytes=64000", "bytes=3200000"))
        else:
            transfer.feed(begin)
            if failure == "missing":
                transfer.feed(chunks[1])
            elif failure == "duplicate":
                transfer.feed(chunks[0])
                transfer.feed(chunks[0])
            else:
                for chunk in chunks:
                    transfer.feed(chunk)
                transfer.pcm[0] ^= 1
                transfer.feed(end)


def test_actual_c_audio_statistics(tmp_path):
    root = Path(__file__).resolve().parents[1]
    main = root / "firmware/esp32/main"
    binary = tmp_path / "audio-test"
    subprocess.run(
        [
            "cc",
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(main),
            str(main / "muse_audio_stats.c"),
            str(root / "tests/firmware_audio.c"),
            "-lm",
            "-o",
            str(binary),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run([str(binary)], check=True, timeout=5)


@pytest.mark.parametrize("corrupt", [False, True])
def test_capture_acknowledges_chunks_and_only_saves_verified_wav(
    tmp_path, monkeypatch, audio_transfer, corrupt
):
    import json
    import stat
    import wave

    from scripts import capture_audio

    pcm, begin, chunks, end = audio_transfer
    if corrupt:
        end = end[:-1] + ("0" if end[-1] != "0" else "1")
    wire = bytearray(("\n".join([begin, *chunks, end]) + "\n").encode())
    writes = []

    class USB:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def reset_input_buffer(self):
            pass

        def write(self, data):
            writes.append(json.loads(data))

        def flush(self):
            pass

        @property
        def in_waiting(self):
            return len(wire)

        def read(self, size):
            chunk = bytes(wire[:size])
            del wire[:size]
            return chunk

    directory = tmp_path / "recordings"
    monkeypatch.setattr(capture_audio, "RECORDINGS", directory)
    monkeypatch.setattr(capture_audio.serial, "Serial", USB)
    if corrupt:
        with pytest.raises(ValueError, match="SHA-256"):
            capture_audio.capture("fake-usb", 1, directory)
        assert not directory.exists()
    else:
        path = capture_audio.capture("fake-usb", 1, directory)
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        with wave.open(str(path), "rb") as wav:
            assert wav.getnchannels() == 2 and wav.getframerate() == 16000
            assert wav.readframes(16000) == pcm
    assert writes[0] == {"capture_seconds": 1}
    assert [command["pcm_ack"] for command in writes[1:]] == [
        min(offset + 768, len(pcm)) for offset in range(0, len(pcm), 768)
    ]


def test_actual_c_speech_endpoint(tmp_path):
    root = Path(__file__).resolve().parents[1]
    main = root / "firmware/esp32/main"
    binary = tmp_path / "endpoint-test"
    subprocess.run(
        [
            "cc",
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(main),
            str(main / "muse_endpoint.c"),
            str(root / "tests/firmware_endpoint.c"),
            "-o",
            str(binary),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run([str(binary)], check=True, timeout=5)


def test_adaptive_usb_transfer_accepts_actual_length_and_verifies_hash(audio_transfer):
    pcm, begin, chunks, end = audio_transfer
    transfer = PCMTransfer(20, variable=True)
    transfer.feed(begin)
    for line in chunks:
        transfer.feed(line)
    assert transfer.feed(end) and bytes(transfer.pcm) == pcm


@pytest.mark.parametrize("size", [0, 1, 1280004, 3200000])
def test_adaptive_transfer_still_rejects_invalid_declared_lengths(size):
    transfer = PCMTransfer(20, variable=True)
    with pytest.raises(ValueError):
        transfer.feed(
            f"MUSE_PCM_BEGIN rate=16000 channels=2 bits=16 bytes={size} sha256=" + "0" * 64
        )


def test_adaptive_capture_cancellation_preserves_next_serial_frame():
    from scripts.capture_audio import CaptureCancelled, receive_pcm

    class USB:
        _muse_pending = b"AUDIO_CAPTURE_CANCELLED reason=limit\nVOICE_STATE Ready\n"

        def write(self, data):
            raise AssertionError("Cancelled audio must not be ACKed")

    device = USB()
    with pytest.raises(CaptureCancelled) as error:
        receive_pcm(device)
    assert error.value.reason == "limit"
    assert device._muse_pending == b"VOICE_STATE Ready\n"
