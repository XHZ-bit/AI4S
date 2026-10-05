"""OpenAI 兼容 LLM 客户端：chat / embeddings，httpx 直连，429/5xx/超时重试。"""
import logging
import time

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
_RETRY_SLEEP = 1.0


def _base() -> str:
    return get_settings().llm_api_base.rstrip("/")


def _api_key() -> str:
    key = get_settings().dashscope_api_key.strip()
    if not key:
        raise RuntimeError("DASHSCOPE_API_KEY is not configured")
    return key


def _retry_delay(attempt: int, response: httpx.Response | None) -> float:
    """优先使用服务端 Retry-After 头，否则线性退避。"""
    if response is not None:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return max(float(retry_after), 0.0)
            except ValueError:
                pass
    return _RETRY_SLEEP * (attempt + 1)


def _post_with_retry(client: httpx.Client, url: str, payload: dict) -> dict:
    last: Exception | None = None
    last_response: httpx.Response | None = None
    for attempt in range(3):
        try:
            resp = client.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {_api_key()}"},
                timeout=get_settings().llm_timeout_seconds,
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            last = exc
            last_response = exc.response
            status = exc.response.status_code
            if status not in (408, 429) and status < 500:
                raise
            logger.warning("llm call failed (attempt %s, status %s)", attempt + 1, status)
        except (httpx.HTTPError, ValueError) as exc:
            # ValueError 覆盖 resp.json() 解析失败（服务端返回非 JSON）
            last = exc
            logger.warning("llm call failed (attempt %s): %s", attempt + 1, exc)
        if attempt < 2:
            time.sleep(_retry_delay(attempt, last_response))
    raise last if isinstance(last, Exception) else RuntimeError("llm call failed")


def _extract_choice(data: dict) -> str:
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("llm response missing choices/content") from exc


def _extract_embeddings(data: dict) -> list[list[float]]:
    items = data.get("data")
    if not isinstance(items, list):
        raise RuntimeError("llm response missing embeddings data")
    try:
        return [item["embedding"] for item in sorted(items, key=lambda d: d["index"])]
    except (KeyError, TypeError) as exc:
        raise RuntimeError("llm response missing embeddings data") from exc


def chat(messages: list[dict], json_mode: bool = False) -> str:
    _api_key()
    payload = {"model": get_settings().llm_model, "messages": messages}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    with httpx.Client() as client:
        data = _post_with_retry(client, f"{_base()}/chat/completions", payload)
    return _extract_choice(data)


def embed(texts: list[str]) -> list[list[float]]:
    _api_key()
    payload = {"model": get_settings().llm_embed_model, "input": texts}
    with httpx.Client() as client:
        data = _post_with_retry(client, f"{_base()}/embeddings", payload)
    return _extract_embeddings(data)
