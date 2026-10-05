"""Opt-in research model transport. No persistence, retries, or prompt logging."""

from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from uuid import uuid4

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
# Keep the metadata audit visible in local/Docker stderr even when the host
# only configures uvicorn's named loggers. Never install a global root handler.
logger.setLevel(logging.INFO)
if not logger.handlers:
    logger.addHandler(logging.StreamHandler())


class ResearchModelError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool = False):
        self.code = code
        self.retryable = retryable
        super().__init__(code)


@dataclass
class CallBudget:
    task_id: str
    calls: int = 0


_budget: ContextVar[CallBudget | None] = ContextVar("research_model_budget", default=None)


@contextmanager
def model_call_scope(task_id: str):
    """Budget applies across all passages in one task; threads are isolated."""
    token = _budget.set(CallBudget(task_id))
    try:
        yield
    finally:
        _budget.reset(token)


def strict_schema(value):
    """Optional fields become required nullable/default-valued fields on the wire."""
    if isinstance(value, list):
        return [strict_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        if key == "default":
            continue
        # These are maps of user-defined names, not schema keywords. A real
        # property named 'default' must not disappear during normalization.
        if key in {"properties", "$defs", "definitions", "patternProperties"} and isinstance(item, dict):
            result[key] = {name: strict_schema(child) for name, child in item.items()}
        elif key in {"enum", "const", "examples"}:
            result[key] = item
        else:
            result[key] = strict_schema(item)
    if result.get("type") == "object":
        result["additionalProperties"] = False
        result["required"] = list(result.get("properties", {}))
    return result


def structured_chat(messages: list[dict], *, schema: dict, prompt_version: str,
                    schema_version: str) -> str:
    settings = get_settings()
    if not settings.research_model_enabled:
        raise ResearchModelError("model_not_authorized")
    if not settings.dashscope_api_key.strip():
        raise ResearchModelError("model_not_configured")
    if len(json.dumps(messages, ensure_ascii=False)) > settings.research_model_max_input_chars:
        raise ResearchModelError("model_input_budget_exceeded")
    budget = _budget.get()
    if budget and budget.calls >= settings.research_model_max_requests:
        raise ResearchModelError("model_request_budget_exceeded")
    if budget:
        budget.calls += 1
    response_format = {"type": settings.research_model_response_format}
    if settings.research_model_response_format == "json_schema":
        response_format["json_schema"] = {
            "name": "research_output", "strict": True, "schema": strict_schema(schema),
        }
    payload = {
        "model": settings.llm_model, "messages": messages,
        "response_format": response_format, "temperature": 0,
        "max_tokens": settings.research_model_max_output_tokens,
    }
    trace = {
        "call_id": uuid4().hex, "task_id": budget.task_id if budget else None,
        "model": settings.llm_model, "prompt_version": prompt_version,
        "schema_version": schema_version, "usage": None, "status": "failed",
    }
    started = time.monotonic()
    try:
        # Never follow redirects with credentials or retry a paid request implicitly.
        with httpx.Client(timeout=settings.research_model_timeout_seconds,
                          follow_redirects=False) as client:
            with client.stream(
                "POST", f"{settings.llm_api_base.rstrip('/')}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {settings.dashscope_api_key}"},
            ) as response:
                if response.status_code != 200:
                    raise ResearchModelError(
                        "model_http_error",
                        retryable=response.status_code in {408, 429} or response.status_code >= 500,
                    )
                chunks = bytearray()
                for chunk in response.iter_bytes():
                    if time.monotonic() - started > settings.research_model_timeout_seconds:
                        raise ResearchModelError("model_timeout", retryable=True)
                    chunks.extend(chunk)
                    if len(chunks) > 2_000_000:
                        raise ResearchModelError("model_response_too_large")
                data = json.loads(chunks)
        if not isinstance(data, dict):
            raise ResearchModelError("model_invalid_response")
        usage = data.get("usage")
        if isinstance(usage, dict):
            trace["usage"] = {
                key: val for key, val in usage.items()
                if key in {"prompt_tokens", "completion_tokens", "total_tokens"}
                and type(val) is int and val >= 0
            }
            details = usage.get("completion_tokens_details")
            if isinstance(details, dict) and type(details.get("reasoning_tokens")) is int:
                if details["reasoning_tokens"] >= 0:
                    trace["usage"]["reasoning_tokens"] = details["reasoning_tokens"]
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ResearchModelError("model_invalid_response")
        choice = choices[0]
        if not isinstance(choice.get("message"), dict):
            raise ResearchModelError("model_invalid_response")
        if choice.get("finish_reason") != "stop":
            raise ResearchModelError("model_incomplete_response")
        content = choice["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise ResearchModelError("model_empty_response")
        trace["status"] = "transport_succeeded"  # Not a scientific quality judgment.
        return content
    except ResearchModelError as exc:
        trace["error_code"] = exc.code
        raise
    except httpx.TimeoutException:
        trace["error_code"] = "model_timeout"
        raise ResearchModelError("model_timeout", retryable=True) from None
    except httpx.HTTPError:
        trace["error_code"] = "model_connection_failed"
        raise ResearchModelError("model_connection_failed", retryable=True) from None
    except (ValueError, KeyError, IndexError, TypeError):
        trace["error_code"] = "model_invalid_response"
        raise ResearchModelError("model_invalid_response") from None
    finally:
        trace["duration_ms"] = round((time.monotonic() - started) * 1000)
        logger.info("research_model_call %s", json.dumps(trace, ensure_ascii=True))
