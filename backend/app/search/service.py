"""语义检索：论文摘要 embedding 入库 + 余弦 top-k（原型期纯 Python 暴力扫描）。"""
import math
import re
import struct

from app.llm.client import embed
from app.db.search_index import available as search_index_available


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


def index_papers(conn, items: list[tuple[str, str]]) -> None:
    """Batch embedding requests, while committing each bounded batch for retry."""
    for offset in range(0, len(items), 20):
        batch = items[offset:offset + 20]
        vectors = embed([text for _, text in batch])
        if len(vectors) != len(batch):
            raise ValueError("embedding count does not match input count")
        conn.executemany("INSERT OR REPLACE INTO paper_embeddings(paper_uid,embedding) VALUES(?,?)",
                         [(uid, _pack(vector)) for (uid, _), vector in zip(batch, vectors, strict=True)])
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


def _excerpt(text: str, terms: list[str], width: int = 280) -> str:
    """Return an exact source slice around a hit, preserving Unicode offsets."""
    folded = text.casefold()
    positions = [folded.find(term) for term in terms if term in folded]
    if not positions:
        return text[:width]
    folded_position = min(positions)
    position, consumed = 0, 0
    # casefold can expand one character (e.g. ß -> ss). Do not use a folded
    # string offset directly to cut the original text.
    for position, character in enumerate(text):
        consumed += len(character.casefold())
        if consumed > folded_position:
            break
    start = max(0, position - 60)
    return text[start:start + width]


def _best_passages(conn, terms: list[str], match: str, indexed: bool) -> dict:
    columns = (
        "d.paper_uid,p.id AS passage_id,p.document_id,p.heading,p.text,p.page,"
        "d.content_hash,paper.title,paper.year,paper.source "
    )
    if indexed:
        rows = conn.execute(
            "SELECT " + columns + ",bm25(passage_search_fts) AS relevance "
            "FROM passage_search_fts f JOIN passages p ON p.id=f.id "
            "JOIN documents d ON d.id=p.document_id JOIN papers paper ON paper.uid=d.paper_uid "
            "WHERE passage_search_fts MATCH ? "
            "ORDER BY relevance ASC,d.created_at DESC,d.rowid DESC,p.ordinal,p.id", (match,),
        )
    else:
        rows = conn.execute(
            "SELECT " + columns + "FROM passages p JOIN documents d ON d.id=p.document_id "
            "JOIN papers paper ON paper.uid=d.paper_uid "
            "ORDER BY d.created_at DESC,d.rowid DESC,p.ordinal,p.id"
        )
    best = {}
    for row in rows:
        body = row["text"].casefold()
        hits = sum(term in body for term in terms)
        if not hits:
            continue  # A heading-only hit is not an original-text quote.
        uid = row["paper_uid"]
        # FTS5 BM25 is lower for better matches. The scan fallback instead
        # favors query coverage, then hit density; it makes no BM25 claim.
        relevance = row["relevance"] if indexed else (
            -hits, -sum(body.count(term) for term in terms) / max(1, len(body)), len(body),
        )
        if uid in best and relevance >= best[uid]["_relevance"]:
            continue
        best[uid] = {**dict(row), "_relevance": relevance}
    return best


def lexical_search(conn, query: str, limit: int = 50) -> list[dict]:
    """Rank papers by metadata hits and attach their best matching source passage."""
    terms = list(dict.fromkeys(re.findall(r"[\w-]+", query.casefold())))[:8]
    if not terms or limit <= 0:
        return []
    indexed = all(len(term) >= 3 for term in terms) and search_index_available(conn)
    match = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
    if indexed:
        rows = conn.execute(
            "SELECT p.uid,p.title,p.abstract,p.year,p.source FROM paper_search_fts f "
            "JOIN papers p ON p.rowid=f.rowid WHERE paper_search_fts MATCH ?", (match,),
        )
    else:
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
        found[row["uid"]] = dict(uid=row["uid"], title=title, year=row["year"],
                                 source=row["source"], score=score,
                                 snippet=_excerpt(abstract, terms),
                                 hit_reason="标题匹配" if title_hits else "摘要匹配")
    passages = _best_passages(conn, terms, match, indexed)
    for uid, row in passages.items():
        if uid not in found:
            found[uid] = dict(uid=uid, title=row["title"], year=row["year"], source=row["source"],
                              score=1, hit_reason=f"原文片段匹配：{row['heading']}")
        quote = _excerpt(row["text"], terms)
        found[uid].update(snippet=quote, quote=quote, passage_id=row["passage_id"],
                          document_id=row["document_id"], page=row["page"],
                          document_version=f"sha256:{row['content_hash']}")
    # Metadata still determines the primary paper rank. Among equal metadata
    # scores, source relevance breaks ties instead of arbitrary UID ordering.
    evidence_order = {uid: rank for rank, uid in enumerate(sorted(
        passages, key=lambda uid: (passages[uid]["_relevance"], uid),
    ))}
    return sorted(found.values(), key=lambda item: (
        -item["score"], evidence_order.get(item["uid"], math.inf), item["uid"],
    ))[:limit]
