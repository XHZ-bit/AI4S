"""语义检索：论文摘要 embedding 入库 + 余弦 top-k（原型期纯 Python 暴力扫描）。"""
import math
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
