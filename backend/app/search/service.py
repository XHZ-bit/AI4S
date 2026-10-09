"""语义检索：论文摘要 embedding 入库 + 余弦 top-k（原型期纯 Python 暴力扫描）。"""
import math
import re
import struct

from app.llm.client import embed


def _pack(v: list[float]) -> bytes:
    return struct.pack(f"{len(v)}d", *v)


def _unpack(b: bytes) -> list[float]:
    return list(struct.unpack(f"{len(b) // 8}d", b))


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


def index_paper(conn, paper_uid: str, text: str) -> None:
    vec = embed([text])[0]
    conn.execute(
        "INSERT OR REPLACE INTO paper_embeddings (paper_uid, embedding) VALUES (?, ?)",
        (paper_uid, _pack(vec)),
    )
    conn.commit()


def semantic_search(conn, query: str, limit: int = 10) -> list[dict]:
    qvec = embed([query])[0]
    rows = conn.execute("SELECT paper_uid, embedding FROM paper_embeddings").fetchall()
    scored = []
    for r in rows:
        score = _cosine(qvec, _unpack(r["embedding"]))
        scored.append({"uid": r["paper_uid"], "score": score})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]


def lexical_search(conn, query: str, limit: int = 50) -> list[dict]:
    """Bounded local title/abstract/passage retrieval with inspectable match text."""
    terms = list(dict.fromkeys(re.findall(r"[\w-]+", query.casefold())))[:8]
    if not terms:
        return []
    rows = conn.execute("SELECT uid,title,abstract,year,source FROM papers").fetchall()
    found = {}
    for row in rows:
        title, abstract = (row["title"] or ""), (row["abstract"] or "")
        title_lower, abstract_lower = title.casefold(), abstract.casefold()
        title_hits = sum(term in title_lower for term in terms)
        abstract_hits = sum(term in abstract_lower for term in terms)
        if not title_hits and not abstract_hits:
            continue
        score = title_hits * 4 + abstract_hits * 2
        term = next((term for term in terms if term in abstract_lower), None)
        start = max(0, abstract_lower.find(term) - 60) if term else 0
        found[row["uid"]] = dict(uid=row["uid"], title=title, year=row["year"],
                                 source=row["source"], score=score,
                                 snippet=abstract[start:start + 280],
                                 hit_reason="标题匹配" if title_hits else "摘要匹配")
    # Source passages can surface papers whose abstract omits the queried term.
    for row in conn.execute(
        "SELECT d.paper_uid,p.heading,p.text FROM passages p JOIN documents d "
        "ON d.id=p.document_id ORDER BY d.created_at DESC,p.ordinal"
    ):
        uid = row["paper_uid"]
        if uid in found:
            continue
        body = row["text"].casefold()
        term = next((term for term in terms if term in body), None)
        if term is None:
            continue
        paper = conn.execute("SELECT title,year,source FROM papers WHERE uid=?", (uid,)).fetchone()
        if paper is None:
            continue
        start = max(0, body.find(term) - 60)
        found[uid] = dict(uid=uid, title=paper["title"], year=paper["year"],
                          source=paper["source"], score=1,
                          snippet=row["text"][start:start + 280],
                          hit_reason=f"原文片段匹配：{row['heading']}")
    return sorted(found.values(), key=lambda item: (-item["score"], item["uid"]))[:limit]
