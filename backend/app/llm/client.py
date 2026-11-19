"""OpenAI 兼容 LLM 客户端：chat / embeddings，httpx 直连，429/5xx/超时重试。"""
import logging
import time
from threading import Lock

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
_RETRY_SLEEP = 1.0
_client = None
_client_lock = Lock()


class ModelOutputTruncated(RuntimeError):
    pass


def shared_client():
    """Reuse TLS setup and keep-alive connections across the bounded workers."""
    global _client
    with _client_lock:
        if _client is None or _client.is_closed:
            _client = httpx.Client(limits=httpx.Limits(max_connections=12, max_keepalive_connections=8),
                                   timeout=httpx.Timeout(60, connect=10, pool=10))
        return _client


def close_client():
    global _client
    with _client_lock:
        client, _client = _client, None
    if client is not None:
        client.close()


def _base() -> str:
    return get_settings().llm_api_base.rstrip("/")


def _api_key() -> str:
    key = get_settings().dashscope_api_key.strip()
    if not key:
        raise RuntimeError("DASHSCOPE_API_KEY is not configured")
    return key


def configured() -> bool:
    """Check the selected provider without resolving DNS or exposing a key."""
    from app import preferences
    from app.tenancy import current_user
    settings = get_settings()
    if settings.offline_mode or (settings.access_mode == "multiuser" and current_user.get() is None):
        return False
    provider = preferences.read().get("provider", {})
    if provider.get("enabled"):
        return bool(provider.get("encrypted_key") and provider.get("base_url") and provider.get("model"))
    return bool((settings.dashscope_api_key or settings.tutor_default_api_key).strip())


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


def _post_with_retry(client: httpx.Client, url: str, payload: dict, provider: dict | None = None,
                     key_override: str | None = None) -> dict:
    last: Exception | None = None
    last_response: httpx.Response | None = None
    for attempt in range(3):
        from app.task_control import check_active
        check_active()
        try:
            if provider:
                target = httpx.URL(url).copy_with(host=provider["address"])
                resp = client.post(
                    target, json=payload,
                    headers={"Authorization": f"Bearer {provider['api_key']}", "Host": provider["host"]},
                    extensions={"sni_hostname": provider["host"]},
                    timeout=httpx.Timeout(get_settings().llm_timeout_seconds, connect=10, pool=10),
                )
            else:
                resp = client.post(
                    url, json=payload, headers={"Authorization": f"Bearer {key_override or _api_key()}"},
                    timeout=httpx.Timeout(get_settings().llm_timeout_seconds, connect=10, pool=10),
                )
            resp.raise_for_status()
            check_active()
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
        choice = data["choices"][0]
        if choice.get("finish_reason") == "length":
            raise ModelOutputTruncated("模型输出达到上限，需要缩短输入后重试")
        content = choice["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("llm response has no text content")
        return content
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
    from app import preferences
    settings = get_settings()
    if settings.offline_mode:
        raise RuntimeError("离线模式不调用模型")
    provider = preferences.provider()
    default_key = settings.tutor_default_api_key if settings.access_mode == "multiuser" else None
    if not provider and not default_key:
        _api_key()
    selected_model = provider["model"] if provider else settings.llm_model
    payload = {"model": selected_model, "messages": messages, "max_tokens": 8192}
    if selected_model.startswith("qwen3"):
        payload["enable_thinking"] = False
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    if provider:
        with httpx.Client(trust_env=False, follow_redirects=False) as client:
            data = _post_with_retry(client, f"{provider['base_url']}/chat/completions", payload, provider)
    else:
        data = _post_with_retry(shared_client(), f"{_base()}/chat/completions", payload, key_override=default_key)
    return _extract_choice(data)


def embedding_identity() -> tuple[str, str]:
    from app import preferences
    settings = get_settings()
    configured = preferences.read().get("provider", {})
    if configured.get("enabled"):
        base = configured.get("base_url", "").rstrip("/")
        name = configured.get("embedding_model", "").strip()
        if not name and base == settings.llm_api_base.rstrip("/"):
            name = settings.llm_embed_model
        if not name:
            raise RuntimeError("请在模型设置中填写该服务的向量模型名称")
        return base, name
    return settings.llm_api_base.rstrip("/"), settings.llm_embed_model


def embed(texts: list[str]) -> list[list[float]]:
    from app import preferences
    settings = get_settings()
    if settings.offline_mode:
        raise RuntimeError("离线模式不调用向量模型")
    base, selected_model = embedding_identity()
    provider = preferences.provider()
    default_key = settings.tutor_default_api_key if settings.access_mode == "multiuser" else None
    if not provider and not default_key:
        _api_key()
    payload = {"model": selected_model, "input": texts}
    if provider:
        with httpx.Client(trust_env=False, follow_redirects=False) as client:
            data = _post_with_retry(client, f"{base}/embeddings", payload, provider)
    else:
        data = _post_with_retry(shared_client(), f"{_base()}/embeddings", payload, key_override=default_key)
    return _extract_embeddings(data)
