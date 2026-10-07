import asyncio
import logging
import secrets
from uuid import uuid4

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from gateway.config import Settings
from gateway.protocol import Ping, incoming
from integrations.llm import TextProvider, create_provider

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, provider: TextProvider | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings()
    provider = provider if provider is not None else create_provider(settings.provider, settings)
    app = FastAPI(title="Muse Gateway", version="0.1.0")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    active_connections = 0

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "project_stage": 4,
            "protocol_version": 1,
            "provider": settings.provider,
        }

    @app.websocket("/ws")
    async def device_socket(socket: WebSocket):
        nonlocal active_connections
        origin = socket.headers.get("origin")
        if origin is not None and origin not in settings.allowed_origins:
            await socket.close(code=1008)
            return
        token = settings.device_token.get_secret_value()
        if token:
            identity = socket.headers.get("x-device-id", "")
            authorization = socket.headers.get("authorization", "")
            if identity != settings.device_id or not secrets.compare_digest(
                authorization.encode(), f"Bearer {token}".encode()
            ):
                await socket.close(code=1008)
                return
        elif socket.client is None or socket.client.host not in {
            "127.0.0.1",
            "::1",
            "testclient",
        }:
            # Also enforce loopback when launched directly through Uvicorn.
            await socket.close(code=1008)
            return
        if active_connections >= settings.max_connections:
            await socket.close(code=1013)
            return
        active_connections += 1
        try:
            await socket.accept()
            await socket.send_json(
                {
                    "type": "hello",
                    "protocol_version": 1,
                    "session_id": str(uuid4()),
                    "capabilities": ["ping", "text"],
                    "provider": settings.provider,
                }
            )
            while True:
                try:
                    frame = await asyncio.wait_for(
                        socket.receive(), timeout=settings.idle_timeout_seconds
                    )
                except TimeoutError:
                    await socket.close(code=1008, reason="Idle timeout")
                    break
                if frame["type"] == "websocket.disconnect":
                    break
                raw = frame.get("text")
                if raw is None:
                    await socket.close(code=1003, reason="Binary audio is not supported in Stage 0")
                    break
                if len(raw.encode("utf-8")) > settings.max_message_bytes:
                    await socket.close(code=1009, reason="Message too large")
                    break
                try:
                    message = incoming.validate_json(raw)
                except ValidationError:
                    await socket.send_json({"type": "error", "code": "invalid_message"})
                    continue
                if isinstance(message, Ping):
                    await socket.send_json({"type": "pong", "id": message.id})
                    continue
                try:
                    reply = await asyncio.wait_for(
                        provider.reply(message.text), timeout=settings.provider_timeout_seconds
                    )
                except Exception:
                    # Do not log user content, credentials, or provider exception bodies.
                    logger.warning("Text provider failed")
                    await socket.send_json(
                        {
                            "type": "error",
                            "id": message.id,
                            "code": "provider_error",
                        }
                    )
                    continue
                await socket.send_json({"type": "text", "id": message.id, "text": reply})
        except WebSocketDisconnect:
            pass
        finally:
            active_connections -= 1

    return app
