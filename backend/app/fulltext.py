"""Fetch only supported public paper hosts; enforce size and redirect bounds."""

import re
from urllib.parse import urlparse
import httpx
from app.db.sqlite import get_paper
from app.db.workspace import stage

_HOSTS = {"arxiv.org", "export.arxiv.org", "www.arxiv.org"}


def fetch_pdf(conn, uid):
    from app.api.papers import _data_dir, _MAX_PDF_BYTES

    paper = get_paper(conn, uid)
    if not paper or not re.fullmatch(r"[A-Za-z0-9._-]+", uid):
        raise ValueError("Unsupported paper identifier")
    url = paper.get("pdf_url")
    if not url:
        raise ValueError("No PDF URL available; please upload the original")
    if url.startswith("http://"):
        url = "https://" + url[len("http://") :]
    stage(conn, uid, "download", "running")
    try:
        with httpx.Client(timeout=45, follow_redirects=False) as client:
            for _ in range(4):
                parts = urlparse(url)
                if (
                    parts.scheme != "https"
                    or parts.hostname not in _HOSTS
                    or parts.port not in (None, 443)
                    or parts.username
                ):
                    raise ValueError("Unsupported PDF host; upload the file directly")
                with client.stream("GET", url) as response:
                    if response.is_redirect:
                        from urllib.parse import urljoin

                        url = urljoin(url, response.headers["location"])
                        continue
                    response.raise_for_status()
                    data = bytearray()
                    for chunk in response.iter_bytes():
                        data.extend(chunk)
                        if len(data) > _MAX_PDF_BYTES:
                            raise ValueError("PDF exceeds 50MB")
                    if not data.startswith(b"%PDF-"):
                        raise ValueError("Remote response is not a PDF")
                    path = _data_dir() / f"{uid}.pdf"
                    if path.exists() and path.read_bytes() != data:
                        raise ValueError(
                            "A different original is already saved; upload the new version separately"
                        )
                    from app.storage import save_original

                    save_original(path, bytes(data))
                    stage(conn, uid, "download", "done")
                    return
            raise ValueError("Too many redirects")
    except Exception as exc:
        stage(conn, uid, "download", "failed", str(exc))
        raise
