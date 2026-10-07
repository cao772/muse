import argparse
import asyncio
import json
import subprocess

import pytest

from gateway import tts
from integrations.local_tts import CANDIDATES, LocalQwenTTS
from integrations.tts import decode_playback_wav, encode_wav


def test_offline_subprocess_stdin_flags_format_and_cleanup(tmp_path, monkeypatch):
    python = tmp_path / "python"
    python.touch()
    paths = []

    def run(args, **kwargs):
        assert args == [str(python), "-m", "integrations.local_tts_worker"]
        assert kwargs["timeout"] == 180 and kwargs["check"]
        assert kwargs["env"]["HF_HUB_OFFLINE"] == "1"
        assert kwargs["env"]["TRANSFORMERS_OFFLINE"] == "1"
        request = json.loads(kwargs["input"])
        assert request["text"] == "你好" and request["voice"] == "Serena"
        from pathlib import Path

        path = Path(request["output"])
        assert path.parent.stat().st_mode & 0o777 == 0o700
        paths.append(path)
        path.write_bytes(encode_wav(b"\0\0" * 16000))

    monkeypatch.setattr(subprocess, "run", run)
    wav = asyncio.run(LocalQwenTTS(python=python).synthesize("你好"))
    assert len(decode_playback_wav(wav)) == 32000
    assert not paths[0].parent.exists()


@pytest.mark.parametrize("failure", ["timeout", "process", "bad", "long"])
def test_offline_failure_sanitized(tmp_path, monkeypatch, failure):
    python = tmp_path / "python"
    python.touch()

    def run(args, **kwargs):
        if failure == "timeout":
            raise subprocess.TimeoutExpired(args, 180, output=b"PRIVATE")
        if failure == "process":
            raise subprocess.CalledProcessError(1, args, stderr=b"PRIVATE")
        from pathlib import Path

        data = encode_wav(b"\0\0" * 80001) if failure == "long" else b"invalid"
        Path(json.loads(kwargs["input"])["output"]).write_bytes(data)

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(RuntimeError) as error:
        asyncio.run(LocalQwenTTS(python=python).synthesize("你好"))
    assert "PRIVATE" not in str(error.value)


@pytest.mark.parametrize("text", ["", " ", "x" * 81, "a\0b"])
def test_offline_rejects_invalid_text_without_loading(text):
    with pytest.raises(ValueError):
        asyncio.run(LocalQwenTTS().synthesize(text))


def test_missing_runtime_has_setup_instructions(tmp_path):
    with pytest.raises(RuntimeError, match="docs/tts-offline.md"):
        asyncio.run(LocalQwenTTS(python=tmp_path / "missing").synthesize("你好"))


def test_audition_generates_three_private_files(tmp_path, monkeypatch):
    calls = []

    class Fake:
        def __init__(self, voice):
            calls.append(voice)

        async def synthesize(self, text):
            assert text == "你好，我是 Muse，有什么可以帮你的吗？"
            return encode_wav(b"\0\0" * 16000)

    monkeypatch.setattr(tts, "LocalQwenTTS", Fake)
    monkeypatch.setattr(tts, "RECORDINGS", tmp_path / "recordings")
    args = argparse.Namespace(provider="qwen-local", audition=True, text=None, voice=None)
    asyncio.run(tts.generate(args))
    assert tuple(calls) == CANDIDATES
    files = list((tmp_path / "recordings" / "tts").glob("*.wav"))
    assert len(files) == 3 and all(p.stat().st_mode & 0o777 == 0o600 for p in files)


def test_default_cli_selects_offline_qwen(monkeypatch):
    monkeypatch.setattr("sys.argv", ["muse-tts"])
    calls = []

    async def generate(args):
        calls.append(args)

    monkeypatch.setattr(tts, "generate", generate)
    tts.main()
    assert calls[0].provider == "qwen-local" and calls[0].voice is None
