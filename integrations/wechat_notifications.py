"""Scoped, read-only batch summaries; never fetch chats or trigger actions."""

from __future__ import annotations

import os
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from integrations.cao import CAOClient, CAOError

OpaqueID = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Category = Literal["mention", "task", "decision", "blocker", "other"]


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    event_id: OpaqueID
    category: Category


class Summary(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[1]
    scope_id: OpaqueID
    authorized: Literal[True]
    status: Literal["available", "stale", "unavailable"]
    last_success_at: str | None
    complete: Literal[True]
    events: list[Event] = Field(max_length=1000)

    def timestamp(self) -> datetime | None:
        if self.last_success_at is None:
            return None
        try:
            result = datetime.fromisoformat(self.last_success_at.replace("Z", "+00:00"))
            if result.tzinfo is None:
                raise ValueError
            return result.astimezone(UTC)
        except ValueError:
            raise CAOError("Invalid WeChat sync timestamp") from None


def unavailable_frame() -> dict:
    return {"status": "unavailable", "count": None, "categories": {}, "sync_age_minutes": None}


class WeChatNotifications:
    """Persist only opaque IDs/categories. A capability/scope change creates a new baseline."""

    def __init__(self, client: CAOClient, scope_id: str, cursor: Path, *, stale_seconds=5400):
        if not client.muse_token:
            raise ValueError("WeChat summaries require a dedicated Muse capability")
        if len(scope_id) != 64 or any(c not in "0123456789abcdef" for c in scope_id):
            raise ValueError("An approved opaque WeChat scope ID is required")
        self.lock = threading.RLock()
        self.client, self.scope_id = client, scope_id
        self.stale_seconds = stale_seconds
        cursor.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        # Use a private regular file; never follow an existing symlink.
        fd = os.open(cursor, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        os.fchmod(fd, 0o600)
        os.close(fd)
        self.db = sqlite3.connect(cursor, check_same_thread=False)
        self.db.executescript(
            "CREATE TABLE IF NOT EXISTS baseline (scope TEXT PRIMARY KEY);"
            "CREATE TABLE IF NOT EXISTS events (scope TEXT, id TEXT, category TEXT,"
            " pending INTEGER, PRIMARY KEY(scope,id));"
        )
        self.frame = unavailable_frame()

    def close(self):
        self.db.close()

    def acknowledge(self):
        with self.lock:
            self._acknowledge()

    def _acknowledge(self):
        if self.frame["status"] != "available":
            return
        with self.db:
            self.db.execute("UPDATE events SET pending=0 WHERE scope=?", (self.scope_id,))
        if self.frame["status"] == "available":
            self.frame = {**self.frame, "count": 0, "categories": {}}

    def observe(self, data: dict, *, now: datetime | None = None) -> dict:
        with self.lock:
            return self._observe(data, now=now)

    def _observe(self, data: dict, *, now: datetime | None = None) -> dict:
        self.frame = unavailable_frame()
        try:
            summary = Summary.model_validate(data)
        except ValidationError:
            raise CAOError("Invalid WeChat summary fields") from None
        if summary.scope_id != self.scope_id:
            raise CAOError("WeChat scope does not match the approved capability")
        timestamp = summary.timestamp()
        now = now or datetime.now(UTC)
        age = (now - timestamp).total_seconds() if timestamp else None
        if age is not None and age < -60:
            raise CAOError("WeChat sync timestamp is in the future")
        if summary.status == "unavailable" or timestamp is None:
            return self.frame
        if summary.status == "stale" or age > self.stale_seconds:
            self.frame = {
                **self.frame,
                "status": "stale",
                "sync_age_minutes": min(9999, max(0, int(age / 60))),
            }
            return self.frame
        ids = [event.event_id for event in summary.events]
        if len(ids) != len(set(ids)):
            raise CAOError("Duplicate IDs in WeChat summary")
        with self.db:
            initialized = self.db.execute(
                "SELECT 1 FROM baseline WHERE scope=?", (self.scope_id,)
            ).fetchone()
            self.db.executemany(
                "INSERT OR IGNORE INTO events VALUES (?,?,?,?)",
                [
                    (self.scope_id, e.event_id, e.category, int(bool(initialized)))
                    for e in summary.events
                ],
            )
            # Complete snapshots remove withdrawn items from pending, never from dedupe history.
            active = set(ids)
            for (event_id,) in self.db.execute(
                "SELECT id FROM events WHERE scope=? AND pending=1", (self.scope_id,)
            ).fetchall():
                if event_id not in active:
                    self.db.execute(
                        "UPDATE events SET pending=0 WHERE scope=? AND id=?",
                        (self.scope_id, event_id),
                    )
            self.db.execute("INSERT OR IGNORE INTO baseline VALUES (?)", (self.scope_id,))
        categories = dict(
            self.db.execute(
                "SELECT category,count(*) FROM events WHERE scope=? AND pending=1 "
                "GROUP BY category",
                (self.scope_id,),
            ).fetchall()
        )
        self.frame = {
            "status": "available",
            "count": min(999, sum(categories.values())),
            "categories": {k: min(999, v) for k, v in categories.items()},
            "sync_age_minutes": min(9999, max(0, int(age / 60))),
        }
        return self.frame

    async def refresh(self):
        self.frame = unavailable_frame()
        try:
            return self.observe(
                await self.client._get("/api/v1/personal-agent/wechat-notifications")
            )
        except (CAOError, sqlite3.Error, OSError):
            return self.frame
