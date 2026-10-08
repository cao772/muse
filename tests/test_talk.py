import argparse
import asyncio
import base64
import hashlib
import json
import struct
import subprocess

import pytest

from gateway import talk
from integrations.tts import TTSOutputTooLong, encode_wav

WAV = talk.input_wav(struct.pack("<hh", 2000, 2000) * 80000)


class STT:
    async def transcribe(self, wav):
        assert wav == WAV
        return "你好 Muse"


class Provider:
    async def reply(self, text):
        assert text == "你好 Muse"
        return "你好，很高兴见到你！"


class TTS:
    async def synthesize(self, text):
        return encode_wav(b"\0\0" * 1600)


def test_full_pipeline_states_and_no_private_text_in_result():
    states, played = [], []

    async def play(pcm):
        played.append(pcm)

    result = asyncio.run(talk.respond(WAV, STT(), Provider(), TTS(), play, status=states.append))
    assert states == ["Transcribing", "Thinking", "Synthesizing", "Playing"]
    assert len(played) == result["segments"] and played
    assert "你好" not in json.dumps(result)


def test_silence_never_calls_stt_or_llm():
    with pytest.raises(ValueError, match="speech"):
        asyncio.run(talk.respond(talk.input_wav(b"\0" * 320000), None, None, None, None))


@pytest.mark.parametrize("answer", ["", "x" * 121, None])
def test_reply_bounds(answer):
    with pytest.raises(ValueError):
        talk.speech_chunks(answer)


def test_chunks_preserve_all_characters():
    text = "你好，Muse。我可以回答你的问题！这是一句超过十二个字符的测试内容。"
    parts = talk.speech_chunks(text)
    assert "".join(parts) == text and all(len(p) <= 20 for p in parts)


def test_long_audio_splits_text_without_truncation():
    leaves = []

    class Long:
        async def synthesize(self, text):
            if len(text) > 4:
                raise TTSOutputTooLong("too long")
            leaves.append(text)
            return encode_wav(b"\0\0" * 1600)

    text = "这是一个超过五秒的测试句子"
    result = asyncio.run(talk.synthesize_bounded(Long(), text))
    assert "".join(leaves) == text and len(result) == len(leaves)


def test_runtime_failure_is_not_retried_or_played():
    calls = []

    class Broken:
        async def synthesize(self, text):
            calls.append(text)
            raise RuntimeError("model unavailable")

    async def play(pcm):
        pytest.fail("should not play incomplete reply")

    with pytest.raises(RuntimeError):
        asyncio.run(talk.respond(WAV, STT(), Provider(), Broken(), play))
    assert len(calls) == 1


def test_llm_timeout_never_synthesizes():
    class Slow:
        async def reply(self, text):
            await asyncio.sleep(1)

    with pytest.raises(TimeoutError):
        asyncio.run(talk.respond(WAV, STT(), Slow(), None, None, provider_timeout=0.001))


def test_process_stt_timeout_and_error_are_sanitized(monkeypatch):
    def run(args, **kwargs):
        assert kwargs["timeout"] == 90 and kwargs["input"] == WAV
        assert kwargs["env"]["HF_HUB_OFFLINE"] == "1"
        raise subprocess.TimeoutExpired(args, 90, stderr=b"PRIVATE")

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(RuntimeError) as error:
        asyncio.run(talk.ProcessWhisper("cached-model").transcribe(WAV))
    assert "PRIVATE" not in str(error.value)


def test_once_owns_single_usb_for_real_capture_and_play_protocol(monkeypatch):
    pcm = struct.pack("<hh", 2000, 2000) * 80000
    digest = hashlib.sha256(pcm).hexdigest()
    frames = [f"MUSE_PCM_BEGIN rate=16000 channels=2 bits=16 bytes=320000 sha256={digest}"]
    frames += [
        f"MUSE_PCM_DATA offset={i} data=" + base64.b64encode(pcm[i : i + 768]).decode()
        for i in range(0, len(pcm), 768)
    ]
    frames += [f"MUSE_PCM_END bytes=320000 sha256={digest}"]
    instances = []

    class USB:
        def __init__(self, *args, **kwargs):
            assert kwargs["exclusive"] is True
            instances.append(self)
            self.pending = bytearray(
                (
                    "MUSE_PCM_DATA offset=768 data=AAAA\n"
                    "MUSE_PCM_END bytes=320000 sha256=old\n"
                    "AUDIO_EXPORT_ERROR\n" + "\n".join(frames) + "\n"
                ).encode()
            )
            self.writes, self.audio = [], bytearray()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def reset_input_buffer(self):
            pass

        def flush(self):
            pass

        @property
        def in_waiting(self):
            return len(self.pending)

        def read(self, n):
            result = bytes(self.pending[:n])
            del self.pending[:n]
            return result

        def write(self, raw):
            m = json.loads(raw)
            self.writes.append(m)
            if "play_begin" in m:
                self.audio.clear()
                self.begin = m
                self.pending += f"MUSE_SPK_READY bytes={m['play_begin']}\n".encode()
            if "play_data" in m:
                assert m["play_data"] == len(self.audio)
                self.audio.extend(base64.b64decode(m["data"]))
                self.pending += f"MUSE_SPK_ACK offset={len(self.audio)}\n".encode()
            if "play_end" in m:
                assert hashlib.sha256(self.audio).hexdigest() == self.begin["sha256"]
                self.pending += (
                    f"MUSE_SPK_PLAYING volume=80\nMUSE_SPK_DONE bytes={len(self.audio)} "
                    f"frames={len(self.audio) // 2} elapsed_ms=1\n"
                ).encode()

    monkeypatch.setattr(talk.serial, "Serial", USB)
    asyncio.run(talk.serve(argparse.Namespace(port="fake", once=True, mock=True)))
    assert len(instances) == 1
    messages = instances[0].writes
    assert messages[0] == {"voice_state": "Thinking", "attention_count": None}
    assert {"voice_state": "Ready", "attention_count": None} in messages
    assert {"pcm_ack": 768} in messages
    assert {"pcm_ack": 320000} in messages
    assert all(m["volume"] == 80 for m in messages if "play_begin" in m)
    assert any("play_end" in m for m in messages)


def test_voice_prompt_only_applies_to_mvp():
    import httpx2 as httpx
    from pydantic import SecretStr

    from gateway.config import Settings
    from integrations.llm import CompatibleProvider

    prompts = []

    def handler(request):
        prompts.append(json.loads(request.content)["messages"][0]["content"])
        return httpx.Response(200, json={"choices": [{"message": {"content": "你好"}}]})

    settings = Settings(_env_file=None, provider="deepseek", llm_api_key=SecretStr("test-only"))
    for voice_mode in [False, True]:
        provider = CompatibleProvider(
            settings, voice_mode=voice_mode, transport=httpx.MockTransport(handler)
        )
        asyncio.run(provider.reply("你好"))
    assert "18个汉字" not in prompts[0] and "18个汉字" in prompts[1]


def test_tts_duration_exit_is_distinct_from_runtime_error(tmp_path, monkeypatch):
    from integrations.local_tts import LocalQwenTTS

    python = tmp_path / "python"
    python.touch()

    def run(args, **kwargs):
        raise subprocess.CalledProcessError(2, args)

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(TTSOutputTooLong):
        asyncio.run(LocalQwenTTS(python=python).synthesize("测试"))
