"""Read roadmap inputs from the evidence ledger, the source of truth for review."""

from app.pipeline.extract import canonical_uid


def _relations(conn, status):
    from app.knowledge.unified import ledger

    for row in ledger(conn, project_id="library"):
        if row["status"] != status or row["kind"] != "relation":
            continue
        payload = row["payload"]
        if not all(
            payload.get(k)
            for k in ("src_type", "src_name", "dst_type", "dst_name", "rel_type")
        ):
            continue
        passage = (
            conn.execute(
                "SELECT text FROM passages WHERE id=?", (row["passage_id"],)
            ).fetchone()
            if row["passage_id"]
            else None
        )
        row["text"] = (
            passage[0]
            if passage
            else (row["quote"] if row["checks"].get("evidence_located") else None)
        )
        if not row["passage_id"] and row["text"]:
            row["passage_id"] = row["evidence"][0]["id"]
        yield row, payload


def audit_rows(conn):
    """Canonical records with the saved source bytes used by mechanical checks."""
    from app.knowledge import store, unified

    rows = []
    for row in unified.ledger(conn, project_id="library"):
        if row["kind"] != "relation":
            continue
        row["payload_json"] = store.encode(row["payload"])
        passage = (
            conn.execute(
                "SELECT * FROM passages WHERE id=?", (row["passage_id"],)
            ).fetchone()
            if row["passage_id"]
            else None
        )
        doc = (
            conn.execute(
                "SELECT paper_uid FROM documents WHERE id=?", (row["document_id"],)
            ).fetchone()
            if row["document_id"]
            else None
        )
        row.update(
            text=passage["text"] if passage else None,
            source_document=passage["document_id"] if passage else None,
            passage_document_id=passage["document_id"] if passage else None,
            document_paper_uid=doc[0] if doc else None,
        )
        if not passage and row["evidence"]:
            evidence = row["evidence"][0]
            block = conn.execute(
                "SELECT data FROM kw_blocks WHERE id=?", (evidence["block_id"],)
            ).fetchone()
            if (
                block
                and not evidence.get("source_missing")
                and not evidence.get("unresolved")
            ):
                text = unified.decode(block[0]).get("text", "")
                quote = evidence.get("quote", "")
                start = text.find(quote) if quote else -1
                row.update(
                    text=text,
                    document_id=evidence["source_id"],
                    source_document=evidence["source_id"],
                    passage_document_id=evidence["source_id"],
                    document_paper_uid=row["paper_uid"],
                    start_offset=start,
                    end_offset=start + len(quote),
                    quote=quote,
                )
        rows.append(row)
    return rows


def _uid(payload, side):
    return payload.get(f"{side}_uid") or canonical_uid(
        payload[f"{side}_type"], payload[f"{side}_name"]
    )


def list_targets(conn, q="", status="human_verified", limit=20):
    found = {}
    for _, p in _relations(conn, status):
        for side in ("src", "dst"):
            if p[f"{side}_type"] not in ("concept", "method"):
                continue
            uid, name = _uid(p, side), p[f"{side}_name"]
            if q.casefold() in f"{uid} {name}".casefold():
                found[uid] = {"uid": uid, "name": name, "type": p[f"{side}_type"]}
    return sorted(found.values(), key=lambda x: (x["name"].casefold(), x["uid"]))[
        :limit
    ]


def resolve_target(conn, name, status="human_verified"):
    matches = [
        x["uid"]
        for x in list_targets(conn, status=status, limit=10000)
        if x["uid"].casefold() == name.casefold()
        or x["name"].casefold() == name.casefold()
    ]
    return matches[0] if len(set(matches)) == 1 else None


def get_prerequisite_edges(conn, status="human_verified"):
    return sorted(
        {
            (_uid(p, "src"), _uid(p, "dst"))
            for row, p in _relations(conn, status)
            if p["rel_type"] == "PREREQUISITE_OF"
            and row["layer"] == "teaching"
            and row["passage_id"]
            and row["text"] is not None
        }
    )


def get_papers_for_concept(conn, concept_uid, status="human_verified"):
    grouped = {}
    for row, p in _relations(conn, status):
        if (
            p["rel_type"] not in ("PROPOSES", "USES", "MENTIONS")
            or _uid(p, "dst") != concept_uid
        ):
            continue
        if p["src_type"] != "paper" or not row["passage_id"] or row["text"] is None:
            continue
        paper = conn.execute(
            "SELECT uid,title,year,code_url FROM papers WHERE uid=?",
            (row["paper_uid"],),
        ).fetchone()
        if not paper or p["src_name"].casefold() != paper["title"].casefold():
            continue
        item = grouped.setdefault(
            paper["uid"],
            {
                **dict(paper),
                "has_resource": bool(paper["code_url"]),
                "evidence_ids": [],
                "knowledge_ids": [],
            },
        )
        item["evidence_ids"].append(row["passage_id"])
        item["knowledge_ids"].append(row["id"])
    return list(grouped.values())
