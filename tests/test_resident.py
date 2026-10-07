import asyncio
import sys

import pytest

from integrations.resident import ResidentModel
from integrations.tts import TTSOutputTooLong

WORKER = """import json,sys,time,os
print(json.dumps({'ready':True}),flush=True)
for line in sys.stdin:
 r=json.loads(line)
 if r.get('hang'): time.sleep(5)
 if r.get('wrong'): r['id']+=1
 v={'id':r['id'],'pid':os.getpid()}
 if r.get('long'):v['error']='too_long'
 if r.get('fail'):v['error']='model'
 print(json.dumps(v),flush=True)
"""


def test_reuse_and_serialized_request_ids():
    async def check():
        model = ResidentModel([sys.executable, "-c", WORKER])
        try:
            await model.start()
            replies = await asyncio.gather(*(model.request({}) for _ in range(10)))
            assert len({r["pid"] for r in replies}) == 1
            assert [r["id"] for r in replies] == list(range(1, 11))
        finally:
            await model.close()

    asyncio.run(check())


@pytest.mark.parametrize("failure", ["hang", "wrong", "fail"])
def test_timeout_or_fault_kills_worker_then_recovers(failure):
    async def check():
        model = ResidentModel([sys.executable, "-c", WORKER], timeout=0.05)
        try:
            first = await model.request({})
            with pytest.raises(RuntimeError):
                await model.request({failure: True})
            assert model.process is None
            next_reply = await model.request({})
            assert next_reply["pid"] != first["pid"] and next_reply["id"] == 3
        finally:
            await model.close()

    asyncio.run(check())


def test_duration_rejection_keeps_healthy_model():
    async def check():
        model = ResidentModel([sys.executable, "-c", WORKER])
        try:
            first = await model.request({})
            with pytest.raises(TTSOutputTooLong):
                await model.request({"long": True})
            assert (await model.request({}))["pid"] == first["pid"]
        finally:
            await model.close()

    asyncio.run(check())


def test_cancellation_terminates_process_without_old_reply():
    async def check():
        model = ResidentModel([sys.executable, "-c", WORKER])
        await model.start()
        request = asyncio.create_task(model.request({"hang": True}))
        await asyncio.sleep(0.03)
        request.cancel()
        with pytest.raises(asyncio.CancelledError):
            await request
        assert model.process is None
        await model.close()

    asyncio.run(check())
