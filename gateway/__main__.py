import uvicorn

from gateway.config import Settings


def main():
    settings = Settings()
    if settings.host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("Stage 0 has no device authentication; use a loopback MUSE_HOST")
    uvicorn.run(
        "gateway.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        ws="websockets-sansio",
        ws_max_size=settings.max_message_bytes,
    )


if __name__ == "__main__":
    main()
