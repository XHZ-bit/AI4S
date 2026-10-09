import json
import uuid
from app.models.roadmap import RoadmapResult


def _normalize(data, rid=None):
    for phase in data.get("phases", []):
        for index, item in enumerate(phase.get("items", [])):
            if not item.get("task_id"):
                item["task_id"] = str(
                    uuid.uuid5(
                        uuid.NAMESPACE_URL, f"atlas:{rid}:{phase['phase']}:{index}"
                    )
                )
    data.setdefault("version", 1)
    return data


def save_roadmap(conn, result, profile):
    data = _normalize(result.model_dump())
    cur = conn.execute(
        "INSERT INTO roadmaps(goal,profile_json,result_json) VALUES(?,?,?)",
        (
            result.goal,
            json.dumps(profile.model_dump(), ensure_ascii=False),
            json.dumps(data, ensure_ascii=False),
        ),
    )
    conn.commit()
    return cur.lastrowid


def get_roadmap(conn, rid):
    row = conn.execute("SELECT * FROM roadmaps WHERE id=?", (rid,)).fetchone()
    if row is None:
        raise LookupError("roadmap not found")
    data = _normalize(json.loads(row["result_json"]), rid)
    data["id"] = rid
    data["created_at"] = row["created_at"]
    parent = conn.execute(
        "SELECT parent_id FROM workflow_roadmap_lineage WHERE child_id=?", (rid,)
    ).fetchone()
    data["parent_id"] = parent["parent_id"] if parent else None
    return RoadmapResult.model_validate(data)


def list_roadmaps(conn):
    return [
        dict(r)
        for r in conn.execute(
            "SELECT id,goal,created_at FROM roadmaps ORDER BY id DESC"
        )
    ]


def update_item_done(
    conn, rid, phase=None, item_index=None, done=False, task_id=None, version=None
):
    conn.execute("BEGIN IMMEDIATE")
    try:
        result = get_roadmap(conn, rid)
        if version is not None and result.version != version:
            raise ValueError("路线已更新，请刷新后重试")
        item = None
        if task_id:
            item = next(
                (i for p in result.phases for i in p.items if i.task_id == task_id),
                None,
            )
        else:
            ph = next((p for p in result.phases if p.phase == phase), None)
            if ph and item_index is not None and 0 <= item_index < len(ph.items):
                item = ph.items[item_index]
        if item is None:
            raise LookupError("item not found")
        item.done = done
        result.version += 1
        conn.execute(
            "UPDATE roadmaps SET result_json=? WHERE id=?",
            (result.model_dump_json(), rid),
        )
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
