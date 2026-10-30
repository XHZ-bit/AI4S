"""Prepare the persistent local demo using pinned local PDFs, without networking.

Existing demo work is validated and kept. Other nonempty directories are refused.
The real-paper roadmap remains an automatic preview; the research project is
explicitly synthetic and its saved plan is human input, not model output.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import re
import sqlite3
import sys
import time
import uuid
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(ROOT / "evaluation" / "research_atlas"))

import fitz  # noqa: E402

from app.db.sqlite import connect, upsert_paper  # noqa: E402
from app.db import projects as project_store  # noqa: E402
from app.db.workspace import save_document  # noqa: E402
from app.models.paper import ParsedPaper, Section  # noqa: E402
from app.roadmap.auto_evaluate import evaluate_candidates  # noqa: E402
from app.knowledge import demo as knowledge_demo  # noqa: E402
from prepare_interaction_fixture import prepare as prepare_synthetic  # noqa: E402
from prepare_second_demo import SOURCES, add_relation  # noqa: E402

MANIFEST = "demo-manifest.json"
KIND = "research-atlas-local-demo"
NOTICE = (
    "本地演示：三篇固定真实论文仅用于原文定位与候选路线预览；"
    "SyntheticProbe 课题、条件和数值为合成资料，方案为人工输入，"
    "不代表科研性能、模型生成成功或学习效果。"
)


def validate_target(directory: Path) -> Path:
    raw = directory.expanduser().absolute()
    for part in [raw, *raw.parents]:
        if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
            raise ValueError(f"Demo directories cannot pass through a link: {part}")
    target = raw.resolve()
    if not target.is_relative_to(ROOT):
        raise ValueError("Choose a demo directory inside this repository")
    for protected in (ROOT / "backend" / "data", ROOT / ".git", ROOT / ".tmp"):
        if target == protected or target.is_relative_to(protected):
            raise ValueError(f"Refusing protected data directory: {target}")
    if target == ROOT or target in ROOT.parents:
        raise ValueError("The repository root cannot be a demo directory")
    return target


def inspect_existing(target: Path) -> dict:
    manifest_path = target / MANIFEST
    if not manifest_path.is_file():
        raise ValueError("Existing nonempty directory has no demo marker; no files were changed")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("kind") != KIND or manifest.get("schema_version") not in {1, 2}:
        raise ValueError("Unrecognized demo marker; no files were changed")
    sources = [] if manifest.get("fixture_kind") == "portable_synthetic" else SOURCES
    expected_uids = {f"arxiv-{source['arxiv']}" for source in sources}
    if (not isinstance(manifest.get("paper_uids"), list)
            or any(not isinstance(uid, str) for uid in manifest["paper_uids"])
            or set(manifest["paper_uids"]) != expected_uids
            or not manifest.get("project_id") or not manifest.get("snapshot_id")
            or not manifest.get("synthetic_paper_uid")):
        raise ValueError("Demo marker is incomplete; existing work was kept")
    database = target / "atlas.db"
    if not database.is_file():
        raise ValueError("Demo database is missing; existing work was not replaced")
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("Demo database integrity check failed; existing work was kept")
        for name in ("papers", "documents", "knowledge", "research_snapshots"):
            conn.execute(f"SELECT 1 FROM {name} LIMIT 1").fetchall()
        project = project_store.get_project(conn, manifest["project_id"])
        snapshot = project_store.get_snapshot(conn, manifest["project_id"], manifest["snapshot_id"])
        if project is None or snapshot is None:
            raise ValueError("Required demo project or snapshot is missing; existing work was kept")
        if project.id != manifest["project_id"] or snapshot.id != manifest["snapshot_id"]:
            raise ValueError("Demo project/snapshot identity mismatch; existing work was kept")
        if snapshot.plan.source_kind.value != "user_input":
            raise ValueError("Synthetic demo snapshot no longer contains the expected manual plan")
        for source in [*sources, {"uid": manifest["synthetic_paper_uid"]}]:
            uid = source.get("uid", f"arxiv-{source.get('arxiv')}")
            if not conn.execute("SELECT 1 FROM papers WHERE uid=?", (uid,)).fetchone():
                raise ValueError(f"Required demo paper is missing: {uid}; no data was replaced")
            document = conn.execute(
                "SELECT * FROM documents WHERE paper_uid=? "
                + ("AND content_hash=? " if "sha256" in source else "") + "ORDER BY created_at LIMIT 1",
                (uid, source["sha256"]) if "sha256" in source else (uid,),
            ).fetchone()
            if document is None or not conn.execute(
                "SELECT 1 FROM passages WHERE document_id=? LIMIT 1", (document["id"],)
            ).fetchone():
                raise ValueError(f"Required demo document/passages are missing: {uid}; no data was replaced")
            path = target / "pdfs" / f"{uid}.pdf"
            if not path.is_file() or not path.resolve().is_relative_to(target) or path.is_symlink():
                raise ValueError(f"Required demo PDF is missing or linked outside the demo: {uid}")
            expected_hash = source.get("sha256", document["content_hash"])
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
                raise ValueError(f"Demo PDF hash mismatch: {uid}; no data was replaced")
        unified = manifest.get("unified_demo")
        if manifest.get("schema_version") == 2:
            if not isinstance(unified, dict) or unified.get("version") not in range(2, knowledge_demo.VERSION + 1) or not unified.get("source_ids"):
                raise ValueError("Unified demo marker is incomplete; existing work was kept")
            for sid in unified.get("source_ids", {}).values():
                row = conn.execute("SELECT a.path,a.hash FROM kw_assets a JOIN kw_sources s ON s.asset_id=a.id WHERE s.id=? AND s.project_id=?", (sid, manifest["project_id"])).fetchone()
                path = Path(row[0]) if row else None
                if not path or not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(target):
                    raise ValueError("Unified demo source is missing or outside its data directory; existing work was kept")
                if hashlib.sha256(path.read_bytes()).hexdigest() != row[1]:
                    raise ValueError("Unified demo source hash mismatch; existing work was kept")
    # Do not reset any database rows: user edits, learning records and extra papers stay.
    return {**manifest, "data_dir": str(target), "database_path": str(database), "reused": True}


def source_cache(cache: Path) -> dict[str, Path]:
    result = {}
    for source in SOURCES:
        name = source["arxiv"]
        options = [cache / f"{name}.pdf", cache / f"arxiv-{name}.pdf"]
        path = next((candidate for candidate in options if candidate.is_file()), None)
        if path is None:
            raise ValueError(f"Pinned PDF cache missing: {name}.pdf in {cache}; no download attempted")
        if hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
            raise ValueError(f"Pinned PDF hash mismatch: {path}; no download attempted")
        result[name] = path
    return result


def seed_papers(directory: Path, cached: dict[str, Path]) -> dict:
    with closing(connect(str(directory / "atlas.db"))) as conn:
        for source in SOURCES:
            uid = f"arxiv-{source['arxiv']}"
            path = directory / "pdfs" / f"{uid}.pdf"
            raw = cached[source["arxiv"]].read_bytes()
            path.write_bytes(raw)
            with fitz.open(stream=raw, filetype="pdf") as doc:
                sections = [Section(heading=f"PDF page {i + 1}", text=page.get_text(), page=i + 1)
                            for i, page in enumerate(doc)]
            upsert_paper(conn, dict(uid=uid, arxiv_id=source["arxiv"].split("v")[0],
                title=source["title"], abstract="", authors=[], year=source["year"],
                venue=None, categories=[], published=None,
                pdf_url=f"https://arxiv.org/pdf/{source['arxiv']}", code_url=None, source="arxiv"))
            did = save_document(conn, uid,
                ParsedPaper(uid=uid, title=source["title"], abstract="", sections=sections),
                content_hash=source["sha256"], filename=path.name)
            passage = next((dict(row) for row in conn.execute(
                "SELECT * FROM passages WHERE document_id=? ORDER BY ordinal", (did,))
                if re.search(re.escape(source["term"]), row["text"], re.IGNORECASE)), None)
            if passage is None:
                raise ValueError(f"Pinned source phrase is missing in {source['arxiv']}")
            add_relation(conn, uid, passage, {"type": source["relation"], "term": source["term"]},
                         (uid, source["title"]), source["concept"])
        dp_uid = f"arxiv-{SOURCES[2]['arxiv']}"
        terms = ["behavior cloning formulation", "diffusion models for visuomotor policy learning"]
        for source, term in zip(SOURCES[:2], terms, strict=True):
            passage = next(dict(row) for row in conn.execute(
                "SELECT pa.* FROM passages pa JOIN documents d ON d.id=pa.document_id "
                "WHERE d.paper_uid=? ORDER BY pa.ordinal", (dp_uid,))
                if term.casefold() in row["text"].casefold())
            add_relation(conn, dp_uid, passage, {"type": "PREREQUISITE_OF", "term": term},
                         source["concept"], ("method:diffusion-policy", "Diffusion Policy"), layer="teaching")
        report = evaluate_candidates(conn, "method:diffusion-policy",
            {"learner A": ["Imitation learning"], "learner B": ["Diffusion models"]})
        if not report["passed"]:
            raise ValueError(f"Pinned roadmap gate failed: {report['failures']}")
    (directory / "auto-evaluation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def prepare(directory: Path, cache: Path, check: bool = False, synthetic_only: bool = False) -> dict:
    target = validate_target(directory)
    if target.exists():
        if not target.is_dir():
            raise ValueError("Demo target is not a directory")
        if any(target.iterdir()):
            existing = inspect_existing(target)
            # Read-only checks and older ad-hoc fixture markers remain untouched.
            # Recognized v1 demo profiles upgrade additively, keeping snapshots,
            # user edits and every existing identifier.
            if not check and existing.get("unified_demo", {}).get("version", 0) < knowledge_demo.VERSION and existing.get("fixture_kind") in {
                    "portable_synthetic", "local_demo_with_pinned_papers_and_synthetic_project"}:
                with closing(connect(str(target / "atlas.db"))) as conn:
                    unified = knowledge_demo.seed(conn, target, existing["project_id"])
                value = {k: v for k, v in existing.items() if k != "reused"}
                value.update(schema_version=2, unified_demo=unified, upgraded_at=datetime.now(UTC).isoformat())
                value["paths"] = {**value.get("paths", {}), **unified["paths"]}
                marker = target / (MANIFEST + ".new")
                marker.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                marker.replace(target / MANIFEST)
                return {**value, "reused": True, "upgraded": True}
            return existing
    if check:
        raise ValueError("Demo is not prepared. Run .\\demo.ps1 -Action Prepare first")
    cached = {} if synthetic_only else source_cache(cache.resolve())
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.parent / f".prepare-{uuid.uuid4().hex}"
    try:
        synthetic = prepare_synthetic(staging)
        report = {"passed": None} if synthetic_only else seed_papers(staging, cached)
        with closing(connect(str(staging / "atlas.db"))) as conn:
            unified = knowledge_demo.seed(conn, staging, synthetic["project_id"], final_directory=target)
        synthetic.update(data_dir=str(target), database_path=str(target / "atlas.db"))
        (staging / "browser-fixture.json").write_text(
            json.dumps(synthetic, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        manifest = {
            "kind": KIND, "schema_version": 2, "created_at": datetime.now(UTC).isoformat(),
            "data_dir": str(target), "database_path": str(target / "atlas.db"),
            "notice": "可移植合成演示：全部资料、方法与数值均为原创测试样例，方案为人工输入，不代表模型质量或科研效果。" if synthetic_only else NOTICE,
            "external_calls_made": False, "scientific_result": False,
            "real_paper_count": 0 if synthetic_only else 3, "synthetic_paper_count": 1,
            "formal_roadmap_count_at_preparation": 0,
            "roadmap_gate_passed": report["passed"],
            "synthetic_project_id": synthetic["project_id"],
            "synthetic_snapshot_id": synthetic["snapshot_id"],
            "project_id": synthetic["project_id"], "snapshot_id": synthetic["snapshot_id"],
            "fixture_kind": "portable_synthetic" if synthetic_only else "local_demo_with_pinned_papers_and_synthetic_project",
            "paper_uids": [] if synthetic_only else [f"arxiv-{source['arxiv']}" for source in SOURCES],
            "synthetic_paper_uid": synthetic["paper_uid"],
            "plan_source_kind": synthetic["plan_source_kind"],
            "unified_demo": unified,
            "paths": {"home": "/", "personalized_roadmap": "/demo/personalized-roadmap",
                      "case": "/cases/diffusion-policy-intro",
                      "synthetic_project": f"/research/{synthetic['project_id']}", **unified["paths"]},
            "source_pdf_sha256": {} if synthetic_only else {source["arxiv"]: source["sha256"] for source in SOURCES},
        }
        (staging / MANIFEST).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        # sqlite3 context managers in the reused fixture commit but do not close;
        # collect their released connections before renaming on Windows.
        gc.collect()
        if target.exists():
            target.rmdir()  # Only the previously validated empty directory can be removed.
        if staging.resolve().parent != target.parent or staging.is_symlink():
            raise ValueError("Unexpected staging path; no directory was moved")
        # Windows scanners can briefly keep a newly written SQLite/PNG handle.
        # Only retry this atomic move into the validated absent target, never
        # delete a competing target or rebuild the fixture over existing work.
        for attempt in range(5):
            try:
                staging.rename(target)
                break
            except PermissionError:
                if attempt == 4 or target.exists():
                    raise
                gc.collect()
                time.sleep(0.15 * (attempt + 1))
        return {**manifest, "reused": False}
    except Exception:
        print(f"Preparation failed. Diagnostic files, if created, remain at {staging}", file=sys.stderr)
        raise


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / ".demo" / "data")
    parser.add_argument("--pdf-dir", type=Path, default=ROOT / ".tmp" / "second-demo-sources")
    parser.add_argument("--check", action="store_true", help="read-only validation; never seed")
    parser.add_argument("--synthetic-only", action="store_true", help="portable original sample; no PDF cache or network required")
    args = parser.parse_args()
    try:
        result = prepare(args.data_dir, args.pdf_dir, args.check, args.synthetic_only)
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
