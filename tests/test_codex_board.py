import asyncio
import copy
from datetime import UTC, datetime
from functools import wraps
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from integrations.cao import CAOError
from integrations.codex_board import CodexBoard, validate


def async_test(function):
    @wraps(function)
    def run(*args, **kwargs):
        return asyncio.run(function(*args, **kwargs))

    return run


def data(n=2, tasks=2):
    return dict(
        schema_version=1,
        status="available",
        scope_id="a" * 64,
        observed_at=datetime.now(UTC).isoformat(),
        coverage=dict(
            registered_project_count=n, observed_codex_project_count=n, untracked_count=None
        ),
        projects=[
            dict(
                project_id=f"p{i}",
                alias=f"P{i:02}",
                tasks=[
                    dict(
                        execution_id=str(uuid4()),
                        repository_id=f"r{i}",
                        title="Test",
                        state="running",
                        source="cao_p2",
                        feedback_allowed=True,
                        formal_completion=False,
                    )
                    for _ in range(tasks)
                ],
            )
            for i in range(n)
        ],
    )


@async_test
async def test_fifty_projects_multiple_sessions_navigation():
    client = AsyncMock()
    client._get.return_value = data(50, 5)
    board = CodexBoard(client)
    await board.refresh()
    for i in range(50):
        assert board.frame()["index"] == i + 1
        for j in range(5):
            assert board.frame()["task_index"] == j + 1
            board.navigate("task", board.revision)
        board.navigate("next", board.revision)
    assert board.frame()["index"] == 1
    old = board.revision - 1
    board.navigate("next", old)
    assert board.frame()["index"] == 1


@pytest.mark.parametrize(
    "field,value",
    [("progress", "Bearer secret"), ("files", ["../private"]), ("formal_completion", True)],
)
def test_rejects_private_or_unverified(field, value):
    d = data()
    d["projects"][0]["tasks"][0][field] = value
    with pytest.raises(ValueError):
        validate(d)


@async_test
async def test_disconnect_unknown_and_pending_cleared():
    client = AsyncMock()
    client._get.return_value = data()
    board = CodexBoard(client)
    await board.refresh()
    board.propose("追加反馈，运行测试")
    client._get.side_effect = CAOError("offline")
    await board.refresh()
    assert board.frame()["status"] == "unavailable" and not board.pending


@async_test
async def test_confirmation_same_session_consumed_once():
    client, execution = AsyncMock(), AsyncMock()
    client._get.return_value = data()
    board = CodexBoard(client)
    await board.refresh()
    p, t = board.selected
    execution.inspect.return_value = dict(project_id=p.project_id, repository_id=t.repository_id)
    execution.request.return_value = {"status": "sent"}
    assert "准备" in board.propose("追加反馈，运行测试")
    assert "已接收" in await board.confirm(execution)
    assert "没有有效" in await board.confirm(execution)
    assert execution.request.await_count == 1
    assert t.execution_id in execution.request.call_args.args[1]


@async_test
async def test_changed_target_or_revocation_never_sends():
    client, execution = AsyncMock(), AsyncMock()
    d = data()
    client._get.return_value = d
    board = CodexBoard(client)
    await board.refresh()
    board.propose("追加反馈，运行测试")
    d = copy.deepcopy(d)
    d["projects"][0]["tasks"][0]["feedback_allowed"] = False
    client._get.return_value = d
    assert "未发送" in await board.confirm(execution)
    execution.request.assert_not_called()


@async_test
async def test_ambiguous_project_no_selection_or_write():
    client = AsyncMock()
    client._get.return_value = data()
    board = CodexBoard(client)
    await board.refresh()
    assert "多个" in board.query("P00和P01的进度")
    assert "不一致" in board.propose("给P01追加反馈")
    assert board.pending is None


@async_test
async def test_no_event_does_not_invent_tests():
    client = AsyncMock()
    client._get.return_value = data(tasks=1)
    board = CodexBoard(client)
    await board.refresh()
    result = board.query("Codex进度")
    assert "暂无详细进度" in result and "暂无真实测试" in result


@async_test
async def test_unknown_named_project_not_current_target():
    client = AsyncMock()
    client._get.return_value = data()
    board = CodexBoard(client)
    await board.refresh()
    assert "尚未授权" in board.query("P99现在做到哪了")
    assert "尚未授权" in board.propose("给P99追加反馈，写测试")
    assert board.pending is None


@async_test
async def test_timeout_not_replayed_or_reproposed():
    client, execution = AsyncMock(), AsyncMock()
    client._get.return_value = data(tasks=1)
    board = CodexBoard(client)
    await board.refresh()
    p, t = board.selected
    execution.inspect.return_value = dict(project_id=p.project_id, repository_id=t.repository_id)
    execution.request.side_effect = CAOError("unknown")
    board.propose("追加反馈，运行测试")
    with pytest.raises(CAOError):
        await board.confirm(execution)
    assert board.pending is None and board.action_state == "unknown"
    assert "不能重复" in board.propose("追加反馈，运行测试")
    assert execution.request.await_count == 1


@async_test
async def test_worst_case_usb_frame_fits_existing_line_budget():
    import json

    client = AsyncMock()
    d = data(tasks=1)
    d["projects"][0]["alias"] = "项" * 24
    d["projects"][0]["tasks"][0].update(
        title="任" * 80, progress="进" * 80, files=["src/" + "x" * 60]
    )
    client._get.return_value = d
    board = CodexBoard(client)
    await board.refresh()
    board.propose("补充测试" * 20)
    frame = {
        "voice_state": "Ready",
        "board": board.frame(),
        "wechat": {
            "status": "available",
            "count": 999,
            "sync_age_minutes": 9999,
            "categories": {"mention": 999, "task": 999, "blocker": 999},
        },
        "attention_count": 999,
        "codex": {"state": "running", "profile": "balanced", "needs_user": True, "title": "x" * 24},
    }
    assert len(json.dumps(frame, ensure_ascii=False).encode()) < 1536


def test_display_subset_matches_compiled_font():
    import re
    from pathlib import Path

    from integrations.codex_board_glyphs import GLYPHS

    font = (
        Path(__file__).resolve().parents[1] / "firmware/esp32/main/muse_pet_zh_18.c"
    ).read_text()
    exported = {chr(int(c, 16)) for c in re.findall(r"/\* U\+([0-9A-Fa-f]+)", font)}
    assert GLYPHS <= exported


@async_test
async def test_named_query_preserves_task_selected_on_screen():
    client = AsyncMock()
    client._get.return_value = data(tasks=3)
    board = CodexBoard(client)
    await board.refresh()
    board.navigate("task", board.revision)
    selected = board.selected[1].execution_id
    board.query("P00现在做到哪里")
    assert board.selected[1].execution_id == selected


@async_test
async def test_desktop_source_is_readonly_and_missing_models_stay_unknown():
    client = AsyncMock()
    d = data(tasks=1)
    d["projects"][0]["tasks"][0].update(
        source="codex_desktop", feedback_allowed=False, state="unknown"
    )
    client._get.return_value = d
    board = CodexBoard(client)
    await board.refresh()
    assert "未知" in board.query("当前用什么模型和推理")
    assert "不具备" in board.propose("追加反馈，运行测试")
