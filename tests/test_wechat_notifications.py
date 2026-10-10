import asyncio
from datetime import UTC, datetime, timedelta

import httpx2 as httpx
import pytest

from integrations.cao import CAOClient, CAOError
from integrations.wechat_notifications import WeChatNotifications

NOW = datetime(2026, 10, 10, 0, tzinfo=UTC)
SCOPE = "a" * 64


def snapshot(*ids, **updates):
    return {
        "schema_version": 1,
        "scope_id": SCOPE,
        "authorized": True,
        "status": "available",
        "last_success_at": NOW.isoformat(),
        "complete": True,
        "events": [{"event_id": f"{i:064x}", "category": "task"} for i in ids],
        **updates,
    }


def observer(tmp_path, **kwargs):
    return WeChatNotifications(
        CAOClient("http://127.0.0.1:8088", muse_token="test-only"),
        kwargs.pop("scope", SCOPE),
        tmp_path / "cursor.sqlite3",
        **kwargs,
    )


def test_baseline_dedupe_restart_viewed_and_removed(tmp_path):
    o = observer(tmp_path)
    assert o.observe(snapshot(1), now=NOW)["count"] == 0
    assert o.observe(snapshot(1, 2), now=NOW)["count"] == 1
    assert o.observe(snapshot(1, 2), now=NOW)["count"] == 1
    o.close()
    o = observer(tmp_path)
    assert o.observe(snapshot(1, 2, 3), now=NOW)["count"] == 2
    o.acknowledge()
    assert o.frame["count"] == 0
    assert o.observe(snapshot(1, 2, 3, 4), now=NOW)["count"] == 1
    assert o.observe(snapshot(1), now=NOW)["count"] == 0
    assert o.observe(snapshot(1, 2, 3, 4), now=NOW)["count"] == 0
    assert o.frame["categories"] == {}
    assert (tmp_path / "cursor.sqlite3").stat().st_mode & 0o777 == 0o600
    o.close()


@pytest.mark.parametrize(
    "update",
    [
        {"text": "private"},
        {"sender": "private"},
        {"group_name": "private"},
        {"scope_id": "b" * 64},
        {"authorized": False},
        {"complete": False},
        {"schema_version": 2},
        {"last_success_at": "invalid"},
        {"last_success_at": NOW.replace(tzinfo=None).isoformat()},
        {"last_success_at": (NOW + timedelta(minutes=2)).isoformat()},
        {"events": [{"event_id": "1" * 64, "category": "task", "text": "private"}]},
        {"events": [{"event_id": "not-opaque", "category": "task"}]},
        {"events": [{"event_id": "1" * 64, "category": "private-chat"}]},
    ],
)
def test_invalid_and_cross_scope_fail_closed(tmp_path, update):
    o = observer(tmp_path)
    o.observe(snapshot(), now=NOW)
    o.observe(snapshot(1), now=NOW)
    with pytest.raises(CAOError) as error:
        o.observe(snapshot(**update), now=NOW)
    assert "private" not in str(error.value)
    assert o.frame["status"] == "unavailable"
    assert o.frame["count"] is None
    o.close()


@pytest.mark.parametrize(
    "update",
    [
        {"status": "stale"},
        {"status": "unavailable"},
        {"last_success_at": None},
        {"last_success_at": (NOW - timedelta(hours=2)).isoformat()},
    ],
)
def test_missing_and_stale_do_not_baseline_or_fake_zero(tmp_path, update):
    o = observer(tmp_path)
    assert o.observe(snapshot(1, **update), now=NOW)["count"] is None
    assert o.observe(snapshot(1), now=NOW)["count"] == 0
    assert o.observe(snapshot(1, 2), now=NOW)["count"] == 1
    o.close()


def test_scope_switch_has_own_silent_baseline(tmp_path):
    o = observer(tmp_path)
    o.observe(snapshot(), now=NOW)
    assert o.observe(snapshot(1), now=NOW)["count"] == 1
    o.close()
    o = observer(tmp_path, scope="b" * 64)
    assert o.observe(snapshot(1, scope_id="b" * 64), now=NOW)["count"] == 0
    o.close()


def test_duplicate_fingerprints_rejected(tmp_path):
    o = observer(tmp_path)
    with pytest.raises(CAOError):
        o.observe(snapshot(1, 1), now=NOW)
    o.close()


def test_scoped_read_only_request_and_revocation(tmp_path):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(403, json={"text": "secret upstream response"})

    client = CAOClient(
        "http://localhost:8088", muse_token="test-only", transport=httpx.MockTransport(handler)
    )
    o = WeChatNotifications(client, SCOPE, tmp_path / "cursor.sqlite3")
    assert asyncio.run(o.refresh())["count"] is None
    assert requests[0].method == "GET"
    assert requests[0].url.path == "/api/v1/personal-agent/wechat-notifications"
    assert requests[0].headers["X-Muse-Token"] == "test-only"
    assert not requests[0].content
    o.close()


def test_private_cursor_has_no_content_and_rejects_symlink(tmp_path):
    o = observer(tmp_path)
    o.observe(snapshot(1), now=NOW)
    o.close()
    data = (tmp_path / "cursor.sqlite3").read_bytes()
    assert b"last_success_at" not in data
    assert b"test-only" not in data
    (tmp_path / "linked").mkdir()
    (tmp_path / "linked" / "cursor.sqlite3").symlink_to(tmp_path / "cursor.sqlite3")
    with pytest.raises(OSError):
        observer(tmp_path / "linked")
