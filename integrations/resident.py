"""One resident model process, serialized requests, bounded RPC and kill-on-failure."""

import asyncio
import json
import os
from pathlib import Path

from integrations.tts import TTSOutputTooLong


class ResidentModel:
    def __init__(self, command, timeout=90):
        self.command, self.timeout = command, timeout
        self.process = None
        self.lock = asyncio.Lock()
        self.sequence = 0

    async def close(self):
        process, self.process = self.process, None
        if process:
            if process.returncode is None:
                process.kill()
            await process.wait()

    async def _start(self):
        if self.process and self.process.returncode is None:
            return
        await self.close()
        env = os.environ.copy()
        env.update(
            HF_HUB_OFFLINE="1",
            TRANSFORMERS_OFFLINE="1",
            HF_HUB_DISABLE_TELEMETRY="1",
            DO_NOT_TRACK="1",
        )
        self.process = await asyncio.create_subprocess_exec(
            *self.command,
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            limit=1048576,
        )
        ready = json.loads(await asyncio.wait_for(self.process.stdout.readline(), 180))
        if ready != {"ready": True}:
            raise RuntimeError("Resident model startup failed")

    async def start(self):
        async with self.lock:
            try:
                await self._start()
            except BaseException:
                await self.close()
                raise

    async def request(self, payload):
        async with self.lock:
            try:
                await self._start()
                self.sequence += 1
                request = {"id": self.sequence, **payload}
                self.process.stdin.write(json.dumps(request).encode() + b"\n")
                await asyncio.wait_for(self.process.stdin.drain(), 5)
                line = await asyncio.wait_for(self.process.stdout.readline(), self.timeout)
                response = json.loads(line)
                if response.get("id") != self.sequence:
                    raise ValueError("Resident model response mismatch")
                if response.get("error") == "too_long":
                    raise TTSOutputTooLong("TTS output exceeds five seconds")
                if "error" in response:
                    raise ValueError("Resident model request failed")
                return response
            except TTSOutputTooLong:
                raise
            except BaseException as error:
                await self.close()
                if isinstance(error, asyncio.CancelledError):
                    raise
                raise RuntimeError(
                    "Resident model failed or timed out; next turn will reload"
                ) from None
