import logging
import time

import httpx

from app.models.paper import normalize_arxiv_id

logger = logging.getLogger(__name__)

_INITIAL_DELAY = 1.0
_HEADERS = {"User-Agent": "research-atlas/0.1 (academic research tool)"}


def _get_with_retry(client: httpx.Client, url: str, params: dict) -> httpx.Response:
    delay = _INITIAL_DELAY
    for attempt in range(4):
        resp = client.get(url, params=params, headers=_HEADERS, timeout=30)
        if resp.status_code != 429:
            return resp
        time.sleep(delay)
        delay *= 2
    logger.warning("S2 rate limit persists after retries for %s", url)
    return resp


def fetch_citations(client: httpx.Client, arxiv_id: str) -> list[str]:
    from app.config import get_settings

    url = f"{get_settings().s2_api_base}/paper/arXiv:{arxiv_id}/citations"
    resp = _get_with_retry(client, url, params={"fields": "externalIds", "limit": 1000})
    if resp.status_code != 200:
        logger.warning("citation fetch failed for arXiv:%s (status %s)", arxiv_id, resp.status_code)
        return []
    refs = []
    for item in resp.json().get("data", []):
        cited = item.get("citedPaper") or {}
        arxiv = (cited.get("externalIds") or {}).get("ArXiv")
        if arxiv:
            refs.append(normalize_arxiv_id(arxiv))
    return refs
