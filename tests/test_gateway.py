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
    assert response.json() == {
        "status": "ok",
        "project_stage": 4,
        "protocol_version": 1,
        "provider": "mock",
    }


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
def test_real_providers_require_credentials(provider):
    with pytest.raises(ValueError, match="MUSE_LLM_API_KEY"):
        create_app(Settings(_env_file=None, provider=provider))


def test_configuration(monkeypatch):
    monkeypatch.setenv("MUSE_PORT", "8765")
    assert Settings(_env_file=None).port == 8765
    monkeypatch.setenv("MUSE_PORT", "0")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_entrypoint_rejects_network_exposure(monkeypatch, tmp_path):
    from gateway.__main__ import main

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MUSE_HOST", "0.0.0.0")
    with pytest.raises(SystemExit, match="loopback"):
        main()


def lan_settings(**overrides):
    return Settings(
        _env_file=None,
        host="0.0.0.0",
        device_token="t" * 40,
        allowed_hosts=["testserver"],
        **overrides,
    )


def auth_headers():
    return {"Authorization": "Bearer " + "t" * 40, "X-Device-ID": "muse-01"}


@pytest.mark.parametrize(
    "headers", [{}, {"Authorization": "Bearer wrong"}, {**auth_headers(), "X-Device-ID": "wrong"}]
)
def test_device_auth_rejects_missing_or_invalid_headers(headers):
    with TestClient(create_app(lan_settings())) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws", headers=headers):
                pass


def test_authenticated_device_and_connection_release():
    with TestClient(create_app(lan_settings(max_connections=1))) as client:
        for _ in range(2):
            with client.websocket_connect("/ws", headers=auth_headers()) as socket:
                assert socket.receive_json()["type"] == "hello"
                with pytest.raises(WebSocketDisconnect):
                    with client.websocket_connect("/ws", headers=auth_headers()):
                        pass
                socket.send_json({"type": "ping", "id": "1"})
                assert socket.receive_json() == {"type": "pong", "id": "1"}


def test_host_and_origin_rejection():
    with TestClient(create_app(lan_settings())) as client:
        assert client.get("/health", headers={"Host": "evil.example"}).status_code == 400
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(
                "/ws", headers={**auth_headers(), "Origin": "https://evil.example"}
            ):
                pass


def test_allowed_origin_and_idle_timeout():
    with TestClient(
        create_app(lan_settings(allowed_origins=["https://muse.local"], idle_timeout_seconds=0.05))
    ) as client:
        with client.websocket_connect(
            "/ws", headers={**auth_headers(), "Origin": "https://muse.local"}
        ) as socket:
            socket.receive_json()
            with pytest.raises(WebSocketDisconnect) as closed:
                socket.receive_json()
            assert closed.value.code == 1008


def test_direct_app_cannot_expose_unauthenticated_websocket():
    with TestClient(create_app(Settings(_env_file=None)), client=("192.168.1.2", 1234)) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws"):
                pass


def test_lan_configuration_requires_explicit_hosts_and_token():
    for options in [
        {"host": "0.0.0.0"},
        {"host": "0.0.0.0", "device_token": "x" * 40, "allowed_hosts": ["*"]},
        {"device_token": "short"},
    ]:
        with pytest.raises(ValidationError):
            Settings(_env_file=None, **options)
