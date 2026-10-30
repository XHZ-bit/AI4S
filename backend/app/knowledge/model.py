"""Bounded platform model transport with durable usage accounting and no retries."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from contextlib import contextmanager
from collections.abc import Callable
from uuid import uuid4

import httpx

from app.config import get_settings
from app.knowledge import store

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
    return bool(s.dashscope_api_key.strip() and not s.offline_mode and s.access_mode == "local" and s.knowledge_model_enabled)


def configured():
    return bool(get_settings().dashscope_api_key.strip())


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
    settings = get_settings()
    request = {"model": settings.llm_model, "temperature": 0.1, "max_tokens": max_tokens,
               "response_format": {"type": "json_object"},
               "messages": [{"role": "system", "content": system},
                            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]}
    if settings.llm_model.startswith("qwen3"):
        request["enable_thinking"] = False
    return request


def _structured(system, payload, budget: Budget, purpose, *, max_tokens=6000, images=None):
    if not available():
        raise ModelUnavailable("平台模型未启用或未配置；已有原文和结构图仍可浏览")
    if budget.calls >= budget.limit:
        raise ModelUnavailable("本次分析达到模型请求上限，已保留完成内容，可继续分析")
    settings = get_settings()
    call_id = uuid4().hex
    request = structured_request(system, payload, max_tokens=max_tokens)
    if len(json.dumps(request, ensure_ascii=False)) > settings.research_model_max_input_chars:
        raise ModelUnavailable("本次输入超出模型输入预算")
    if images:
        if len(images) > 4 or any(not isinstance(item, str) or not item.startswith('data:image/png;base64,') or len(item) > 1_500_000 for item in images):
            raise ModelUnavailable("公式图像超过单次处理范围")
        request['messages'][1]['content'] = [{'type': 'text', 'text': json.dumps(payload, ensure_ascii=False)}] + [
            {'type': 'image_url', 'image_url': {'url': item}} for item in images]
    budget.calls += 1
    budget.usage["calls"] += 1
    trace = {"model": settings.llm_model, "status": "running", "seconds": None, "usage": {}}
    with store.connection(budget.project_id) as conn:
        conn.execute("INSERT INTO kw_model_calls VALUES(?,?,?,?,?,?,?)", (call_id, budget.project_id, budget.run_id, purpose, "running", store.encode(trace), store.now()))
    started = time.monotonic()
    try:
        with httpx.Client(timeout=httpx.Timeout(settings.llm_timeout_seconds, connect=15), follow_redirects=False, trust_env=False) as client:
            response = client.post(settings.llm_api_base.rstrip("/") + "/chat/completions", json=request,
                                   headers={"Authorization": "Bearer " + settings.dashscope_api_key})
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
