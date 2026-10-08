from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import re
import stat
from pathlib import Path
from typing import Any

import httpx2 as httpx

AUTH_BASE = "https://auth.openai.com"
API_BASE = "https://api.openai.com/v1"
PLAN_SCOPE = "chatgpt.tokens.use.direct"


class ChatGPTPlanError(RuntimeError):
    """Sanitized ChatGPT plan error; never exposes tokens or upstream bodies."""


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _parse_saved_at(value: Any) -> dt.datetime:
    if not isinstance(value, str):
        raise ChatGPTPlanError("ChatGPT plan credentials are invalid")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ChatGPTPlanError("ChatGPT plan credentials are invalid") from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(dt.UTC)


def _scope_set(value: Any) -> set[str]:
    if isinstance(value, str):
        return {item for item in value.split() if item}
    if isinstance(value, list):
        return {str(item) for item in value if item}
    return set()


def _response_text_from_completed(event: dict[str, Any]) -> str:
    response = event.get("response")
    if not isinstance(response, dict):
        return ""
    chunks: list[str] = []
    for item in response.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if isinstance(part, dict) and part.get("type") == "output_text":
                text = part.get("text")
                if isinstance(text, str):
                    chunks.append(text)
    return "".join(chunks)


class ChatGPTPlanProvider:
    """Responses API provider backed by Sign in with ChatGPT plan credentials."""

    def __init__(
        self,
        credential_path: str,
        *,
        preferred_model: str = "",
        timeout_seconds: float = 60,
        web_context: str = "low",
        transport=None,
        voice_mode: bool = False,
    ):
        if web_context not in {"low", "medium", "high"}:
            raise ValueError("ChatGPT web context must be low, medium or high")
        self.credential_path = Path(credential_path).expanduser()
        self.preferred_model = preferred_model.strip()
        self.timeout_seconds = timeout_seconds
        self.web_context = web_context
        self.transport = transport
        self.voice_mode = voice_mode
        self._refresh_lock = asyncio.Lock()
        self._model_cache: str | None = None
        self.last_model = ""
        self.last_used_web = False
        self.last_reasoning_effort = "medium"

    def _read_credentials(self) -> dict[str, Any]:
        try:
            if os.name != "nt":
                mode = stat.S_IMODE(self.credential_path.stat().st_mode)
                if mode & 0o077:
                    raise ChatGPTPlanError(
                        "ChatGPT plan credential file permissions are too broad; require 0600"
                    )
            data = json.loads(self.credential_path.read_text())
        except ChatGPTPlanError:
            raise
        except (OSError, ValueError, TypeError):
            raise ChatGPTPlanError(
                "ChatGPT plan is not connected; run the local sign-in command first"
            ) from None

        if not isinstance(data, dict):
            raise ChatGPTPlanError("ChatGPT plan credentials are invalid")
        required = ("client_id", "access_token", "refresh_token", "expires_in", "saved_at")
        if any(not data.get(key) for key in required):
            raise ChatGPTPlanError("ChatGPT plan credentials are invalid")
        scopes = _scope_set(data.get("scopes") or data.get("scope"))
        if PLAN_SCOPE not in scopes:
            raise ChatGPTPlanError("ChatGPT plan usage was not authorized")
        return data

    def _write_credentials(self, data: dict[str, Any]) -> None:
        self.credential_path.parent.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            os.chmod(self.credential_path.parent, 0o700)
        temp = self.credential_path.with_suffix(self.credential_path.suffix + ".tmp")
        payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        with open(temp, "w", opener=lambda path, flags: os.open(path, flags, 0o600)) as handle:
            handle.write(payload)
        if os.name != "nt":
            os.chmod(temp, 0o600)
        temp.replace(self.credential_path)
        if os.name != "nt":
            os.chmod(self.credential_path, 0o600)

    @staticmethod
    def _needs_refresh(data: dict[str, Any]) -> bool:
        saved_at = _parse_saved_at(data["saved_at"])
        try:
            expires_in = int(data["expires_in"])
        except (TypeError, ValueError):
            raise ChatGPTPlanError("ChatGPT plan credentials are invalid") from None
        return _utc_now() >= saved_at + dt.timedelta(seconds=max(60, expires_in - 90))

    async def _refresh(self, data: dict[str, Any]) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                transport=self.transport,
                follow_redirects=False,
            ) as client:
                response = await client.post(
                    AUTH_BASE + "/api/accounts/oauth/token",
                    data={
                        "grant_type": "refresh_token",
                        "client_id": data["client_id"],
                        "refresh_token": data["refresh_token"],
                        "resource": API_BASE,
                    },
                )
            if response.status_code != 200:
                raise ChatGPTPlanError(
                    f"ChatGPT plan token refresh failed (HTTP {response.status_code})"
                )
            refreshed = response.json()
        except ChatGPTPlanError:
            raise
        except Exception:
            raise ChatGPTPlanError("ChatGPT plan token refresh failed") from None

        if not isinstance(refreshed, dict):
            raise ChatGPTPlanError("ChatGPT plan token refresh returned invalid data")
        merged = dict(data)
        for key in (
            "access_token",
            "refresh_token",
            "id_token",
            "token_type",
            "expires_in",
            "earliest_refresh_at",
        ):
            if refreshed.get(key) is not None:
                merged[key] = refreshed[key]
        if isinstance(refreshed.get("scope"), str):
            merged["scopes"] = sorted(_scope_set(refreshed["scope"]))
        if PLAN_SCOPE not in _scope_set(merged.get("scopes")):
            raise ChatGPTPlanError("ChatGPT plan usage is no longer authorized")
        if not merged.get("access_token") or not merged.get("refresh_token"):
            raise ChatGPTPlanError("ChatGPT plan token refresh returned invalid data")
        merged["saved_at"] = _utc_now().isoformat()
        self._write_credentials(merged)
        return merged

    async def _credentials(self) -> dict[str, Any]:
        data = self._read_credentials()
        if not self._needs_refresh(data):
            return data
        async with self._refresh_lock:
            current = self._read_credentials()
            if not self._needs_refresh(current):
                return current
            return await self._refresh(current)

    async def _select_model(self, access_token: str) -> str:
        if self._model_cache:
            return self._model_cache
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                transport=self.transport,
                follow_redirects=False,
            ) as client:
                response = await client.get(
                    API_BASE + "/models",
                    headers={"Authorization": "Bearer " + access_token},
                )
            if response.status_code != 200:
                raise ChatGPTPlanError(
                    f"ChatGPT model catalog failed (HTTP {response.status_code})"
                )
            data = response.json()
        except ChatGPTPlanError:
            raise
        except Exception:
            raise ChatGPTPlanError("ChatGPT model catalog request failed") from None

        raw_models = data.get("models") if isinstance(data, dict) else None
        if raw_models is None and isinstance(data, dict):
            raw_models = data.get("data")
        models: list[str] = []
        for item in raw_models or []:
            if not isinstance(item, dict):
                continue
            slug = item.get("slug") or item.get("id")
            visibility = item.get("visibility")
            if isinstance(slug, str) and (visibility in {None, "list"}):
                models.append(slug)
        if not models:
            raise ChatGPTPlanError("No ChatGPT plan models are currently available")
        if self.preferred_model:
            if self.preferred_model not in models:
                raise ChatGPTPlanError("Configured ChatGPT model is not available to this account")
            selected = self.preferred_model
        else:
            selected = models[0]
        self._model_cache = selected
        return selected

    async def reply(
        self,
        text: str,
        *,
        use_web: bool = False,
        reasoning_effort: str = "medium",
        reflection: bool = False,
    ) -> str:
        if reasoning_effort not in {"low", "medium", "high"}:
            raise ValueError("reasoning_effort must be low, medium or high")
        self.last_used_web = False
        self.last_model = ""
        credentials = await self._credentials()
        model = await self._select_model(str(credentials["access_token"]))
        instructions = (
            "你是 Muse 的高级研究脑。优先回答事实和结论，不泄露内部推理过程。"
            "如果使用网页搜索，基于检索到的最新来源回答。"
        )
        if reflection:
            instructions += (
                "用户还要求反思隐藏问题：先回答当前问题，再指出至多一个真正重要、被忽略的更深层问题；"
                "没有就不要硬凑。"
            )
        if self.voice_mode:
            instructions += (
                "回复将由语音朗读，请用自然中文，结论优先，尽量控制在100个汉字以内，不用Markdown。"
            )

        payload: dict[str, Any] = {
            "model": model,
            "instructions": instructions,
            "input": [{"role": "user", "content": text}],
            "reasoning": {"effort": reasoning_effort},
            "store": False,
            "stream": True,
        }
        if use_web:
            payload["tools"] = [
                {
                    "type": "web_search",
                    "search_context_size": self.web_context,
                }
            ]
            payload["tool_choice"] = "required"

        self.last_used_web = False
        self.last_model = ""
        deltas: list[str] = []
        completed_text = ""
        saw_completed = False
        searched = False
        received_bytes = 0
        try:
            async with asyncio.timeout(self.timeout_seconds):
                async with httpx.AsyncClient(
                    timeout=self.timeout_seconds,
                    transport=self.transport,
                    follow_redirects=False,
                ) as client:
                    async with client.stream(
                        "POST",
                        API_BASE + "/responses",
                        headers={"Authorization": "Bearer " + str(credentials["access_token"])},
                        json=payload,
                    ) as response:
                        if response.status_code != 200:
                            raise ChatGPTPlanError(
                                f"ChatGPT plan request failed (HTTP {response.status_code})"
                            )
                        async for line in response.aiter_lines():
                            received_bytes += len(line.encode())
                            if received_bytes > 2_000_000:
                                raise ChatGPTPlanError("ChatGPT plan stream exceeded size limit")
                            if not line.startswith("data:"):
                                continue
                            raw = line[5:].strip()
                            if not raw or raw == "[DONE]":
                                continue
                            try:
                                event = json.loads(raw)
                            except ValueError:
                                raise ChatGPTPlanError(
                                    "ChatGPT plan stream contained invalid data"
                                ) from None
                            if not isinstance(event, dict):
                                raise ChatGPTPlanError("ChatGPT plan stream contained invalid data")
                            event_type = event.get("type")
                            if event_type == "response.output_text.delta":
                                delta = event.get("delta")
                                if isinstance(delta, str):
                                    deltas.append(delta)
                            elif event_type == "response.web_search_call.completed":
                                searched = True
                            elif event_type == "response.completed":
                                saw_completed = True
                                completed_text = _response_text_from_completed(event)
                                result = event.get("response") or {}
                                searched = searched or any(
                                    isinstance(item, dict)
                                    and item.get("type") == "web_search_call"
                                    and item.get("status") == "completed"
                                    for item in result.get("output") or []
                                )
                            elif event_type in {"response.failed", "response.incomplete", "error"}:
                                raise ChatGPTPlanError("ChatGPT plan request did not complete")
        except ChatGPTPlanError:
            raise
        except Exception:
            raise ChatGPTPlanError("ChatGPT plan request failed or timed out") from None

        answer = "".join(deltas).strip() or completed_text.strip()
        if not saw_completed:
            raise ChatGPTPlanError("ChatGPT plan stream ended without a completed response")
        if use_web and not searched:
            raise ChatGPTPlanError("ChatGPT response did not confirm a completed web search")
        if not answer:
            raise ChatGPTPlanError("ChatGPT plan returned an empty response")
        if self.voice_mode:
            answer = re.sub(r"\[([^]]+)\]\(https?://[^)]+\)", r"\1", answer)
            answer = re.sub(r"https?://\S+", "", answer).strip()
        if self.voice_mode and len(answer) > 120:
            answer = answer[:119].rstrip() + "…"

        self.last_model = model
        self.last_used_web = searched
        self.last_reasoning_effort = reasoning_effort
        return answer
