"""Private line RPC loop: reserve protocol stdout and suppress library output."""

import json
import os
import sys

from integrations.tts import TTSOutputTooLong


def run(load, handle):
    protocol = os.fdopen(os.dup(sys.stdout.fileno()), "w", buffering=1)
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    model = load()
    protocol.write(json.dumps({"ready": True}) + "\n")
    for line in sys.stdin.buffer:
        if len(line) > 1048576:
            raise ValueError("RPC input too large")
        request = json.loads(line)
        try:
            response = {"id": request["id"], **handle(model, request)}
        except TTSOutputTooLong:
            response = {"id": request["id"], "error": "too_long"}
        except Exception:
            response = {"id": request["id"], "error": "model"}
        protocol.write(json.dumps(response) + "\n")
