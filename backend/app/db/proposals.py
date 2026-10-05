import json
import struct


def _pack(v: list[float]) -> bytes:
    # 使用 double（8 字节）而非 float（4 字节），保证往返精度满足 1e-9 容差
    return struct.pack(f"{len(v)}d", *v)


def _unpack(b: bytes) -> list[float]:
    return list(struct.unpack(f"{len(b) // 8}d", b))


def save_proposal(conn, paper_uid, kind, payload, confidence, embedding=None):
    existing = conn.execute(
        "SELECT id, payload_json FROM extraction_proposals "
        "WHERE paper_uid=? AND kind=? AND status IN ('pending', 'approved', 'auto_merged')",
        (paper_uid, kind),
    ).fetchall()
    for row in existing:
        previous = json.loads(row["payload_json"])
        identity = (
            ("type", "name")
            if kind == "entity"
            else ("rel_type", "src_name", "dst_name")
        )
        same_source = (
            payload.get("passage_id")
            and previous.get("passage_id") == payload["passage_id"]
            and previous.get("evidence") == payload.get("evidence")
            and all(previous.get(k) == payload.get(k) for k in identity)
        )
        if previous == payload or same_source:
            return row["id"]
    cur = conn.execute(
        "INSERT INTO extraction_proposals (paper_uid, kind, payload_json, confidence, embedding) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            paper_uid,
            kind,
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            confidence,
            _pack(embedding) if embedding else None,
        ),
    )
    conn.commit()
    return cur.lastrowid


def _row_to_dict(row):
    d = dict(row)
    d["payload"] = json.loads(d["payload_json"])
    del d["payload_json"]
    if d.get("embedding"):
        d["embedding"] = _unpack(d["embedding"])
    return d


def list_proposals(conn, status="pending", kind=None):
    sql = "SELECT * FROM extraction_proposals WHERE status=?"
    args = [status]
    if kind:
        sql += " AND kind=?"
        args.append(kind)
    sql += " ORDER BY confidence DESC, id"
    return [_row_to_dict(r) for r in conn.execute(sql, args).fetchall()]


def get_proposal(conn, pid):
    row = conn.execute(
        "SELECT * FROM extraction_proposals WHERE id=?", (pid,)
    ).fetchone()
    return _row_to_dict(row) if row else None


def update_status(conn, pid, status, edited_payload=None):
    if edited_payload is not None:
        conn.execute(
            "UPDATE extraction_proposals SET status=?, payload_json=? WHERE id=?",
            (status, json.dumps(edited_payload, ensure_ascii=False), pid),
        )
    else:
        conn.execute(
            "UPDATE extraction_proposals SET status=? WHERE id=?", (status, pid)
        )
    conn.commit()


def save_entity_vector(conn, uid, name, embedding):
    conn.execute(
        "INSERT OR REPLACE INTO entity_vectors (uid, name, vector) VALUES (?, ?, ?)",
        (uid, name, _pack(embedding)),
    )
    conn.commit()


def all_entity_vectors(conn):
    return [
        {"uid": r["uid"], "name": r["name"], "embedding": _unpack(r["vector"])}
        for r in conn.execute("SELECT uid, name, vector FROM entity_vectors").fetchall()
    ]
