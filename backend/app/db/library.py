"""Personal paper flags, independent of reading progress and mastery records."""

import json
from datetime import datetime, timezone


def init_library(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS paper_library (
      paper_uid TEXT PRIMARY KEY REFERENCES papers(uid) ON DELETE CASCADE,
      starred INTEGER NOT NULL DEFAULT 0 CHECK(starred IN (0,1)),
      read_later INTEGER NOT NULL DEFAULT 0 CHECK(read_later IN (0,1)),
      updated_at TEXT NOT NULL);
    """)


_FROM = "FROM papers p LEFT JOIN paper_library l ON l.paper_uid=p.uid"
_COLUMNS = """p.uid,p.title,p.abstract,p.authors_json,p.year,p.source,
    p.parse_status,p.created_at,coalesce(l.starred,0) AS starred,
    coalesce(l.read_later,0) AS read_later,l.updated_at AS library_updated_at"""


def _view(row):
    item = dict(row)
    item["authors"] = json.loads(item.pop("authors_json"))
    item["starred"] = bool(item["starred"])
    item["read_later"] = bool(item["read_later"])
    return item


def paper_item(conn, uid):
    row = conn.execute(f"SELECT {_COLUMNS} {_FROM} WHERE p.uid=?", (uid,)).fetchone()
    if row is None:
        raise LookupError("论文不存在")
    return _view(row)


def list_papers(conn, *, filter="all", q="", parse_status=None, limit=20, offset=0):
    if filter not in ("all", "starred", "read_later"):
        raise ValueError("无效的资料架筛选")
    where = "WHERE (p.title LIKE ? OR p.abstract LIKE ?)"
    args = [f"%{q}%", f"%{q}%"]
    if filter != "all":
        where += f" AND l.{filter}=1"
    if parse_status:
        where += " AND p.parse_status=?"
        args.append(parse_status)
    # Keep the total and page in one read snapshot during concurrent flag edits.
    conn.execute("BEGIN")
    try:
        total = conn.execute(f"SELECT COUNT(*) {_FROM} {where}", args).fetchone()[0]
        rows = conn.execute(
            f"SELECT {_COLUMNS} {_FROM} {where} ORDER BY p.created_at DESC,p.uid LIMIT ? OFFSET ?",
            [*args, limit, offset],
        ).fetchall()
        result = {"total": total, "items": [_view(row) for row in rows]}
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise


def summary(conn):
    row = conn.execute(
        "SELECT COUNT(*) AS 'all',coalesce(SUM(l.starred),0) AS starred,"
        f"coalesce(SUM(l.read_later),0) AS read_later {_FROM}"
    ).fetchone()
    return dict(row)


def set_flags(conn, uid, changes):
    if not changes or changes.keys() - {"starred", "read_later"}:
        raise ValueError("至少指定一个资料架标记")
    if any(type(value) is not bool for value in changes.values()):
        raise ValueError("资料架标记必须为布尔值")
    # Serialize the existence check and merge: changing one flag must not undo a
    # simultaneous update to the other flag from another browser or connection.
    conn.execute("BEGIN IMMEDIATE")
    try:
        current = paper_item(conn, uid)
        if any(current[key] != value for key, value in changes.items()):
            flags = {key: changes.get(key, current[key]) for key in ("starred", "read_later")}
            conn.execute(
                "INSERT INTO paper_library(paper_uid,starred,read_later,updated_at) VALUES(?,?,?,?) "
                "ON CONFLICT(paper_uid) DO UPDATE SET starred=excluded.starred,"
                "read_later=excluded.read_later,updated_at=excluded.updated_at",
                (uid, int(flags["starred"]), int(flags["read_later"]),
                 datetime.now(timezone.utc).isoformat(timespec="microseconds")),
            )
        item = paper_item(conn, uid)
        conn.commit()
        return item
    except Exception:
        conn.rollback()
        raise
