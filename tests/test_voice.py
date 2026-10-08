import asyncio
import io
import struct
import wave

import httpx2 as httpx
import pytest
from pydantic import SecretStr

from gateway.config import Settings
from gateway.voice import process_wav
from integrations.llm import CompatibleProvider, MockProvider, ProviderError
from integrations.stt import MockSTT, stereo_wav_to_mono


def wav_bytes(samples, *, rate=16000, channels=2):
    stream = io.BytesIO()
    with wave.open(stream, "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(struct.pack("<" + "h" * len(samples), *samples))
    return stream.getvalue()


def config():
    return Settings(_env_file=None, provider="deepseek", llm_api_key=SecretStr("test-only"))


def test_mono_conversion_full_scale_and_different_channels():
    audio = stereo_wav_to_mono(wav_bytes([32767, 32767, -32768, -32768, 100, 300, -1, 0]))
    assert struct.unpack("<4h", audio.pcm) == (32767, -32768, 200, -1)
    assert audio.seconds == 4 / 16000


@pytest.mark.parametrize(
    "data",
    [
        b"invalid",
        wav_bytes([0, 0], rate=48000),
        wav_bytes([0], channels=1),
        wav_bytes([0] * 640002),
        wav_bytes([0, 1])[:-1],
        b"x" * 2097153,
    ],
    ids=["invalid", "rate", "channels", "duration", "truncated", "size"],
)
def test_invalid_wav(data):
    with pytest.raises(ValueError):
        stereo_wav_to_mono(data)


def test_offline_voice_pipeline_and_stt_only():
    data = wav_bytes([2, 4] * 16000)
    result = asyncio.run(process_wav(data, MockSTT("你好 Muse"), MockProvider()))
    assert result["transcript"] == "你好 Muse"
    assert result["reply"] == "[mock] 收到：你好 Muse"
    assert result["audio_seconds"] == 1
    result = asyncio.run(process_wav(data, MockSTT("你好")))
    assert result["reply"] is None
    assert result["llm_seconds"] is None


def test_compatible_request_and_response():
    def handler(request):
        import json

        body = json.loads(request.content)
        assert request.url == "https://api.deepseek.com/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-only"
        assert body["messages"][-1]["content"] == "你好"
        assert body["model"] == "deepseek-flash"
        assert body["thinking"] == {"type": "disabled"}
        assert body["stream"] is False
        return httpx.Response(200, json={"choices": [{"message": {"content": "你好，我是 Muse"}}]})

    provider = CompatibleProvider(config(), transport=httpx.MockTransport(handler))
    assert asyncio.run(provider.reply("你好")) == "你好，我是 Muse"


@pytest.mark.parametrize("status", [401, 402, 429, 500, 302])
def test_upstream_errors_sanitized(status):
    provider = CompatibleProvider(
        config(),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(status, text="PRIVATE test-only upstream body")
        ),
    )
    with pytest.raises(ProviderError) as error:
        asyncio.run(provider.reply("PRIVATE user text"))
    assert str(status) in str(error.value)
    assert "PRIVATE" not in str(error.value)
    assert "test-only" not in str(error.value)


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"choices": []},
        {"choices": [{"message": {"content": ""}}]},
        {"choices": [{"message": {"content": None}}]},
    ],
)
def test_invalid_response_sanitized(response):
    provider = CompatibleProvider(
        config(), transport=httpx.MockTransport(lambda request: httpx.Response(200, json=response))
    )
    with pytest.raises(ProviderError, match="invalid response"):
        asyncio.run(provider.reply("你好"))


def test_transport_timeout_sanitized():
    def handler(request):
        raise httpx.ReadTimeout("PRIVATE test-only")

    provider = CompatibleProvider(config(), transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError) as error:
        asyncio.run(provider.reply("你好"))
    assert "PRIVATE" not in str(error.value)


@pytest.mark.parametrize(
    "url",
    [
        "http://api.deepseek.com",
        "https://user:pass@api.deepseek.com",
        "https://api.deepseek.com?key=private",
        "https://other.example",
    ],
)
def test_deepseek_credential_destination(url):
    settings = config().model_copy(update={"llm_base_url": url})
    with pytest.raises(ValueError):
        CompatibleProvider(settings)


def test_voice_provider_deadline():
    class SlowProvider:
        async def reply(self, text):
            await asyncio.sleep(1)

    with pytest.raises(TimeoutError):
        asyncio.run(process_wav(wav_bytes([0, 0]), MockSTT(), SlowProvider(), 0.001))
