"""Bounded read-only polling; outputs metadata, never task text or credentials."""

import argparse
import asyncio
import json

from gateway.config import Settings
from integrations.attention import AttentionObserver
from integrations.cao import CAOClient, CAOError


async def observe(cycles: int, interval: float, *, focus=False, do_not_disturb=False):
    settings = Settings()
    client = CAOClient(
        settings.cao_base_url,
        settings.cao_timeout_seconds,
        muse_token=settings.cao_muse_token.get_secret_value(),
    )
    observer = AttentionObserver()
    for index in range(cycles):
        try:
            snapshot = await client.attention()
            candidates = observer.observe(snapshot, focus=focus, do_not_disturb=do_not_disturb)
            print(
                json.dumps(
                    dict(
                        observation="current_snapshot",
                        count=snapshot.get("count"),
                        candidate_ids=[i["item_id"] for i in candidates],
                        auto_interrupt=False,
                    )
                ),
                flush=True,
            )
        except CAOError:
            print(
                json.dumps(dict(observation="unavailable", candidate_ids=[], auto_interrupt=False)),
                flush=True,
            )
        if index + 1 < cycles:
            await asyncio.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description="Read-only Muse attention observation")
    parser.add_argument("--cycles", type=int, default=1, choices=range(1, 11))
    parser.add_argument("--interval", type=float, default=10)
    parser.add_argument("--focus", action="store_true")
    parser.add_argument("--do-not-disturb", action="store_true")
    args = parser.parse_args()
    if not 5 <= args.interval <= 60:
        parser.error("interval must be 5–60 seconds")
    asyncio.run(
        observe(args.cycles, args.interval, focus=args.focus, do_not_disturb=args.do_not_disturb)
    )


if __name__ == "__main__":
    main()
