"""Bounded platform model transport with durable usage accounting and no retries."""

from __future__ import annotations

import json
import threading
import time
from datetime import UTC, datetime, timedelta
from dataclasses import dataclass, field
from contextlib import contextmanager
from collections.abc import Callable
from uuid import uuid4

import httpx

from app.config import get_settings
from app.knowledge import store
from app import preferences
from app.tenancy import current_user

_slots = threading.BoundedSemaphore(2)


class ModelUnavailable(RuntimeError):
    pass


@dataclass
class Budget:
    project_id: str
    run_id: str
    limit: int = 16
    calls: int = 0
    usage: dict = field(default_factory=lambda: {"calls": 0, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0})
    check_active: Callable | None = None


def available():
    s = get_settings()
    if s.offline_mode or not s.knowledge_model_enabled:
        return False
    if s.access_mode == "multiuser" and current_user.get() is None:
        return False
    return configured()


def configured():
    provider = preferences.read().get("provider", {})
    if provider.get("enabled"):
        return bool(provider.get("encrypted_key") and provider.get("base_url") and provider.get("model"))
    settings = get_settings()
    return bool((settings.dashscope_api_key or settings.tutor_default_api_key).strip())


def identity():
    """Return the selected model identity without reading or revealing credentials."""
    provider = preferences.read().get("provider", {})
    if provider.get("enabled"):
        return provider.get("model", ""), provider.get("base_url", "")
    settings = get_settings()
    return settings.llm_model, settings.llm_api_base


def usage_for(project_id, run_id):
    total = {'calls': 0, 'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0}
    with store.connection(project_id) as conn:
        for row in conn.execute('SELECT data FROM kw_model_calls WHERE project_id=? AND run_id=?', (project_id, run_id)):
            usage = json.loads(row[0]).get('usage', {})
            total['calls'] += 1
            for key, supplied in [('input_tokens', 'prompt_tokens'), ('output_tokens', 'completion_tokens'), ('total_tokens', 'total_tokens')]:
                total[key] += usage.get(supplied, 0) if isinstance(usage.get(supplied, 0), int) else 0
    return total


@contextmanager
def operation(project_id, key):
    from fastapi import HTTPException
    with store.connection(project_id) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT status FROM kw_operations WHERE project_id=? AND operation_key=?", (project_id, key)).fetchone()
        if row and row[0] == "running":
            raise HTTPException(409, "该内容正在生成，请等待完成后查看；不会重复调用模型")
        conn.execute("INSERT OR REPLACE INTO kw_operations VALUES(?,?,?,?)", (project_id, key, "running", store.now()))
    try:
        yield
    finally:
        with store.connection(project_id) as conn:
            conn.execute("UPDATE kw_operations SET status='finished',updated_at=? WHERE project_id=? AND operation_key=?", (store.now(), project_id, key))


def structured(system, payload, budget: Budget, purpose, *, max_tokens=6000, images=None):
    with _slots:
        if budget.check_active:
            budget.check_active()
        return _structured(system, payload, budget, purpose, max_tokens=max_tokens, images=images)


def structured_request(system, payload, *, max_tokens=6000):
    """Build the exact text request used by transport and context budgeting."""
    selected_model, _ = identity()
    request = {"model": selected_model, "temperature": 0.1, "max_tokens": max_tokens,
               "response_format": {"type": "json_object"},
               "messages": [{"role": "system", "content": system},
                            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]}
    if selected_model.startswith("qwen3"):
        request["enable_thinking"] = False
    return request


def _structured(system, payload, budget: Budget, purpose, *, max_tokens=6000, images=None):
    if not available():
        raise ModelUnavailable("平台模型未启用或未配置；已有原文和结构图仍可浏览")
    if budget.calls >= budget.limit:
        raise ModelUnavailable("本次分析达到模型请求上限，已保留完成内容，可继续分析")
    settings = get_settings()
    try:
        custom = preferences.provider()
    except (ValueError, KeyError) as exc:
        raise ModelUnavailable(str(exc)) from None
    selected_model = custom["model"] if custom else settings.llm_model
    base = custom["base_url"] if custom else settings.llm_api_base
    key = custom["api_key"] if custom else settings.dashscope_api_key or settings.tutor_default_api_key
    call_id = uuid4().hex
    request = structured_request(system, payload, max_tokens=max_tokens)
    request["model"] = selected_model
    if selected_model.startswith("qwen3"):
        request["enable_thinking"] = False
    else:
        request.pop("enable_thinking", None)
    if len(json.dumps(request, ensure_ascii=False)) > settings.research_model_max_input_chars:
        raise ModelUnavailable("本次输入超出模型输入预算")
    if images:
        if len(images) > 4 or any(not isinstance(item, str) or not item.startswith('data:image/png;base64,') or len(item) > 1_500_000 for item in images):
            raise ModelUnavailable("公式图像超过单次处理范围")
        request['messages'][1]['content'] = [{'type': 'text', 'text': json.dumps(payload, ensure_ascii=False)}] + [
            {'type': 'image_url', 'image_url': {'url': item}} for item in images]
    trace = {"model": selected_model, "status": "running", "seconds": None, "usage": {}}
    with store.connection(budget.project_id) as conn:
        hourly_limit = settings.knowledge_hourly_request_limit
        if settings.access_mode == "multiuser" and hourly_limit:
            conn.execute("BEGIN IMMEDIATE")
            since = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
            count = conn.execute(
                "SELECT COUNT(*) FROM kw_model_calls WHERE created_at>=?", (since,)
            ).fetchone()[0]
            if count >= hourly_limit:
                raise ModelUnavailable(f"当前账号已达到每小时 {hourly_limit} 次知识模型请求上限，请稍后再试")
        conn.execute("INSERT INTO kw_model_calls VALUES(?,?,?,?,?,?,?)", (call_id, budget.project_id, budget.run_id, purpose, "running", store.encode(trace), store.now()))
    budget.calls += 1
    budget.usage["calls"] += 1
    started = time.monotonic()
    try:
        with httpx.Client(timeout=httpx.Timeout(settings.llm_timeout_seconds, connect=15), follow_redirects=False, trust_env=False) as client:
            url = httpx.URL(base.rstrip("/") + "/chat/completions")
            headers = {"Authorization": "Bearer " + key}
            extensions = {}
            if custom:
                url = url.copy_with(host=custom["address"])
                headers["Host"] = custom["host"]
                extensions["sni_hostname"] = custom["host"]
            response = client.post(url, json=request, headers=headers, extensions=extensions)
            response.raise_for_status()
            data = response.json()
        usage = data.get("usage") or {}
        for target, field in [("input_tokens", "prompt_tokens"), ("output_tokens", "completion_tokens"), ("total_tokens", "total_tokens")]:
            if isinstance(usage.get(field), int):
                budget.usage[target] += usage[field]
        trace["usage"] = usage
        choice = data["choices"][0]
        if choice.get("finish_reason") == "length":
            raise ValueError("模型输出被截断，已保留先前结果")
        text = choice["message"]["content"]
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        result = json.loads(text)
        # Some vision providers return a bare array despite JSON-object mode.
        # Normalize only this narrow shape; formula validation still checks every region.
        if purpose == 'formula_transcription' and isinstance(result, list) and all(isinstance(item, dict) for item in result):
            result = {'formulas': result}
        if not isinstance(result, dict):
            raise ValueError("模型未返回结构化对象")
        trace["status"] = "succeeded"
        return result
    except httpx.HTTPStatusError as exc:
        trace["status"] = "failed"
        trace['error'] = f"模型服务返回 HTTP {exc.response.status_code}，未自动重复请求"
        raise ModelUnavailable(trace['error']) from None
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
        trace["status"] = "failed"
        trace['error'] = str(exc)[:500] if isinstance(exc, ValueError) else "模型响应不可用，未自动重复请求"
        raise ModelUnavailable(trace['error']) from None
    finally:
        trace["seconds"] = round(time.monotonic() - started, 3)
        with store.connection(budget.project_id) as conn:
            conn.execute("UPDATE kw_model_calls SET status=?,data=? WHERE id=?", (trace["status"], store.encode(trace), call_id))
