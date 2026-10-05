"""Exercise a running gateway with a hardware-free device client."""

import argparse
import asyncio
import json

from websockets.asyncio.client import connect


async def simulate(url: str):
    # Device traffic is direct; do not inherit the host's HTTP/SOCKS proxy.
    async with connect(url, open_timeout=5, proxy=None) as socket:

        async def receive():
            return json.loads(await asyncio.wait_for(socket.recv(), timeout=5))

        hello = await receive()
        assert hello["type"] == "hello" and hello["protocol_version"] == 1, hello
        await socket.send(json.dumps({"type": "ping", "id": "ping-1"}))
        assert await receive() == {"type": "pong", "id": "ping-1"}
        await socket.send(json.dumps({"type": "text", "id": "text-1", "text": "你好 Muse"}))
        reply = await receive()
        assert reply == {"type": "text", "id": "text-1", "text": "[mock] 收到：你好 Muse"}, reply
        print("PASS: WebSocket handshake → ping/pong → mock text reply")
        print(reply["text"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="ws://127.0.0.1:8000/ws")
    asyncio.run(simulate(parser.parse_args().url))
