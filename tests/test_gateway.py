import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.websockets import WebSocketDisconnect

from gateway.app import create_app
from gateway.config import Settings


@pytest.fixture
def client():
    with TestClient(create_app(Settings(_env_file=None, provider="mock"))) as client:
        yield client


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "stage": 0, "provider": "mock"}


def test_device_round_trip_and_reconnect(client):
    sessions = []
    for _ in range(2):
        with client.websocket_connect("/ws") as socket:
            hello = socket.receive_json()
            assert hello["type"] == "hello"
            assert hello["protocol_version"] == 1
            assert hello["capabilities"] == ["ping", "text"]
            sessions.append(hello["session_id"])
            socket.send_json({"type": "ping", "id": "1"})
            assert socket.receive_json() == {"type": "pong", "id": "1"}
            socket.send_json({"type": "text", "id": "2", "text": "你好"})
            assert socket.receive_json() == {"type": "text", "id": "2", "text": "[mock] 收到：你好"}
    assert sessions[0] != sessions[1]


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "[]",
        "null",
        '{"type":"tool","id":"1"}',
        '{"type":"text","id":"1","text":""}',
        '{"type":"ping","id":1}',
        '{"type":"ping","id":"1","extra":true}',
    ],
)
def test_invalid_message_does_not_kill_session(client, raw):
    with client.websocket_connect("/ws") as socket:
        socket.receive_json()
        socket.send_text(raw)
        assert socket.receive_json() == {"type": "error", "code": "invalid_message"}
        socket.send_json({"type": "ping", "id": "next"})
        assert socket.receive_json() == {"type": "pong", "id": "next"}


@pytest.mark.parametrize("binary,code", [(True, 1003), (False, 1009)])
def test_unsupported_or_oversized_frames(client, binary, code):
    with client.websocket_connect("/ws") as socket:
        socket.receive_json()
        if binary:
            socket.send_bytes(b"audio")
        else:
            socket.send_text("中" * 16384)
        with pytest.raises(WebSocketDisconnect) as closed:
            socket.receive_json()
        assert closed.value.code == code


def test_provider_failure_is_reported_without_details():
    class BrokenProvider:
        async def reply(self, text):
            raise RuntimeError("secret provider details")

    with TestClient(
        create_app(Settings(_env_file=None, provider="mock"), BrokenProvider())
    ) as client:
        with client.websocket_connect("/ws") as socket:
            socket.receive_json()
            socket.send_json({"type": "text", "id": "1", "text": "hello"})
            assert socket.receive_json() == {"type": "error", "id": "1", "code": "provider_error"}
            socket.send_json({"type": "ping", "id": "2"})
            assert socket.receive_json() == {"type": "pong", "id": "2"}


@pytest.mark.parametrize("provider", ["deepseek", "qwen", "openai-compatible"])
def test_unimplemented_providers_fail_explicitly(provider):
    with pytest.raises(ValueError, match="not implemented"):
        create_app(Settings(_env_file=None, provider=provider))


def test_configuration(monkeypatch):
    monkeypatch.setenv("MUSE_PORT", "8765")
    assert Settings(_env_file=None).port == 8765
    monkeypatch.setenv("MUSE_PORT", "0")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_entrypoint_rejects_network_exposure(monkeypatch):
    from gateway.__main__ import main

    monkeypatch.setenv("MUSE_HOST", "0.0.0.0")
    with pytest.raises(SystemExit, match="loopback"):
        main()
