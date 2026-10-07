import uvicorn

from gateway.config import Settings


def main():
    try:
        settings = Settings()
    except ValueError:
        raise SystemExit(
            "Invalid configuration: non-loopback access requires device authentication"
        )
    uvicorn.run(
        "gateway.app:create_app",
        factory=True,
        proxy_headers=False,
        host=settings.host,
        port=settings.port,
        ws="websockets-sansio",
        ws_max_size=settings.max_message_bytes,
    )


if __name__ == "__main__":
    main()
