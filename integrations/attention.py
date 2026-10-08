"""Read-only attention observation. No speech, notifications or task execution."""

from __future__ import annotations

import time

from integrations.cao import CAOError


class AttentionObserver:
    def __init__(self):
        self.seen: set[str] = set()
        self.initialized = False
        self.last_observed_at: float | None = None

    def observe(self, snapshot: dict, *, focus=False, do_not_disturb=False) -> list[dict]:
        items = snapshot.get("items")
        if (
            snapshot.get("snapshot_only") is not True
            or snapshot.get("auto_interrupt") is not False
            or not isinstance(items, list)
            or len(items) > 50
        ):
            raise CAOError("CAO attention snapshot is invalid")
        current: dict[str, dict] = {}
        for item in items:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("item_id"), str)
                or len(item["item_id"]) != 24
                or any(c not in "0123456789abcdef" for c in item["item_id"])
                or item.get("needs_user") is not True
            ):
                raise CAOError("CAO attention item is invalid")
            current[item["item_id"]] = item
        # First observation establishes a baseline, avoiding historical alert floods.
        new = [item for key, item in current.items() if key not in self.seen]
        deliver = new if self.initialized and not focus and not do_not_disturb else []
        # Truncated feeds cannot establish disappearance. Never replay suppressed items.
        self.seen.update(current)
        if snapshot.get("truncated") is False:
            self.seen.intersection_update(current)
        self.initialized = True
        self.last_observed_at = time.monotonic()
        return deliver

    def is_fresh(self, max_age_seconds=30) -> bool:
        return self.last_observed_at is not None and (
            time.monotonic() - self.last_observed_at <= max_age_seconds
        )
