import logging
from uuid import uuid4

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from gateway.config import Settings
from gateway.protocol import Ping, incoming
from integrations.llm import TextProvider, create_provider

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, provider: TextProvider | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings()
    provider = provider if provider is not None else create_provider(settings.provider)
    app = FastAPI(title="Muse Gateway", version="0.1.0")

    @app.get("/health")
    async def health():
        return {"status": "ok", "stage": 0, "provider": settings.provider}

    @app.websocket("/ws")
    async def device_socket(socket: WebSocket):
        await socket.accept()
        try:
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
                frame = await socket.receive()
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
                    reply = await provider.reply(message.text)
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

    return app
