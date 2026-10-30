"""Resumable source analysis with durable stages and a separate parser process."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

from fastapi import HTTPException

from app.config import get_settings
from app.knowledge import extraction, model, store
from app.tasks import submit_task

_parse_slot = threading.Semaphore(1)
_queue_slots = threading.BoundedSemaphore(16)
_futures = {}
_future_lock = threading.Lock()


class Cancelled(RuntimeError):
    pass


def enqueue(pid, sid, *, retry=False):
    with store.connection(pid) as conn:
        src = store.source(conn, pid, sid)
        latest = src.get("analysis")
        if not retry and latest and latest["status"] in {"succeeded", "partial"}:
            return latest
        value, fresh = store.create_run(conn, pid, sid)
    if fresh:
        if not _queue_slots.acquire(blocking=False):
            with store.connection(pid) as conn:
                store.update_run(conn, pid, value["id"], status="interrupted", errors=["分析队列已满，原文已保存，请稍后继续"])
            raise HTTPException(429, "分析队列已满，原文已保存")
        try:
            future = submit_task(analyze, pid, sid, value["id"], retry)
            key = (pid, value["id"])
            with _future_lock:
                _futures[key] = future
            def finished(_future):
                _queue_slots.release()
                with _future_lock:
                    _futures.pop(key, None)
            future.add_done_callback(finished)
        except Exception:
            _queue_slots.release()
            with store.connection(pid) as conn:
                store.update_run(conn, pid, value["id"], status="interrupted", errors=["后台执行器暂不可用，原文已保存"])
            raise
    return value


def _cancel_check(pid, rid):
    with store.connection(pid) as conn:
        value = store.run(conn, pid, rid)
        src = store.source(conn, pid, value["source_id"], include_removed=True)
    if value["status"] == "cancelled" or src["removed"]:
        raise Cancelled("分析已取消")


def _kill_parser(process):
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=10, check=False)
    else:
        process.kill()
    try:
        process.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


def parse_file(path, kind, check_cancel):
    from time import monotonic
    while not _parse_slot.acquire(timeout=0.5):
        check_cancel()
    process = None
    try:
        check_cancel()
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        env["KNOWLEDGE_USE_DOCLING"] = "true" if get_settings().knowledge_use_docling else "false"
        if model.available() and get_settings().knowledge_formula_vision_enabled:
            # Layout stays local; the bounded platform call below transcribes
            # formula regions without loading a second CPU language model.
            env['PAPERSTRIDE_FORMULA_BUDGET_SECONDS'] = '0'
        env.pop("DASHSCOPE_API_KEY", None)
        command = [sys.executable, "-X", "utf8", "-m", "app.knowledge.parser_worker", "--input", str(path), "--kind", kind]
        if not get_settings().knowledge_use_docling:
            command.append("--no-docling")
        process = subprocess.Popen(command, cwd=Path(__file__).parents[2], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        started = monotonic()
        while True:
            try:
                stdout, stderr = process.communicate(timeout=1)
                break
            except subprocess.TimeoutExpired:
                check_cancel()
                if monotonic() - started > get_settings().knowledge_parser_timeout_seconds:
                    raise RuntimeError("结构解析超时；已保留原文，可稍后继续")
        if process.returncode:
            # Parser diagnostics are local; never return machine paths or arbitrary source text as errors.
            raise RuntimeError("结构解析进程失败，请检查本地解析依赖和模型文件")
        try:
            result = json.loads(stdout.decode("utf-8"))
        except (ValueError, UnicodeError):
            raise RuntimeError("结构解析返回内容不合法") from None
        if not isinstance(result, dict) or not isinstance(result.get("blocks"), list):
            raise RuntimeError("结构解析缺少内容块")
        return result
    finally:
        if process and process.poll() is None:
            _kill_parser(process)
        _parse_slot.release()


def _bridge_paper(conn, src, result, blocks):
    if not src.get("paper_uid"):
        return
    from app.db.workspace import save_document
    from app.models.paper import ParsedPaper, Section
    parsed = ParsedPaper(uid=src["paper_uid"], title=result["title"], abstract=result.get("abstract", ""),
                         sections=[Section(heading=b.get("heading", ""), text=b.get("text", ""), page=b.get("page"), kind=b["kind"], metadata=b.get("metadata", {})) for b in blocks])
    # A distinct parser representation version preserves legacy frozen passage IDs.
    from app.knowledge.source_files import bind_document_file, bridge_digest
    digest = bridge_digest(src, result, blocks)
    document_id = save_document(conn, src["paper_uid"], parsed, content_hash=digest, filename=src["filename"])
    bind_document_file(conn, document_id, src, digest)
    conn.execute("UPDATE papers SET title=?,parse_status='parsed',abstract=CASE WHEN ?!='' THEN ? ELSE abstract END WHERE uid=?",
                 (result["title"], parsed.abstract, parsed.abstract, src["paper_uid"]))


def analyze(pid, sid, rid, retry=False):
    budget = model.Budget(pid, rid, get_settings().research_model_max_requests)
    budget.check_active = lambda: _cancel_check(pid, rid)
    warnings, errors = [], []
    stages = {"save": "done", "parse": "pending", "extract": "pending", "graph": "pending"}
    try:
        _cancel_check(pid, rid)
        with store.connection(pid) as conn:
            src = store.source(conn, pid, sid)
            asset = conn.execute("SELECT path FROM kw_assets WHERE id=?", (src["asset_id"],)).fetchone()
            cached = conn.execute("SELECT data FROM kw_parses WHERE asset_id=?", (src["asset_id"],)).fetchone()
            stages["parse"] = "running"
            store.update_run(conn, pid, rid, status="running", stages=stages, progress=0.15)
        # Continue resumes failed semantic stages; successful structural parsing is reusable.
        result = json.loads(cached[0]) if cached else parse_file(Path(asset[0]), src["kind"], lambda: _cancel_check(pid, rid))
        _cancel_check(pid, rid)
        from app.knowledge.formulas import enrich_result
        try:
            result = enrich_result(Path(asset[0]), result, budget)
        except model.ModelUnavailable as exc:
            warnings.append(str(exc))
        warnings.extend(result.get("warnings", []))
        if not result["blocks"]:
            raise RuntimeError("未解析到可用内容；原文件已保留")
        with store.connection(pid) as conn:
            store.put_parse(conn, src["asset_id"], result)
            src = store.update_source(conn, pid, sid, {"title": src["title"] if src.get("title_user_edited") else result.get("title") or src["title"], "quality": result.get("quality", {}), "parser": result.get("parser", "unknown")})
            blocks = store.source_blocks(conn, src["asset_id"])
            _bridge_paper(conn, src, result, blocks)
            extraction.structural_graph(conn, src, blocks)
            quality = result.get("quality", {})
            stages["parse"] = "partial" if quality.get("status") in {"partial", "fallback"} or ("fallback" in result.get("parser", "").casefold()) else "done"
            stages["graph"] = "done"
            stages["extract"] = "running"
            store.update_run(conn, pid, rid, stages=stages, progress=0.35, warnings=warnings)
        def progress(done, total, usage, issues):
            _cancel_check(pid, rid)
            with store.connection(pid) as conn:
                store.update_run(conn, pid, rid, progress=0.35 + 0.55 * done / max(total, 1), usage=usage, warnings=list(dict.fromkeys(warnings + issues)),
                                 coverage={"completed_batches": done, "total_batches": total})
        try:
            result_extract = extraction.extract(pid, sid, rid, budget, lambda: _cancel_check(pid, rid), progress)
            warnings.extend(result_extract["warnings"])
            stages["extract"] = "done" if not result_extract["warnings"] and result_extract["nodes"] else "partial"
            if not result_extract["nodes"]:
                warnings.append("未取得有引用支持的语义知识，当前显示资料结构，请检查全文内容或继续分析")
        except model.ModelUnavailable as exc:
            stages["extract"] = "partial"
            errors.append(str(exc))
        _cancel_check(pid, rid)
        with store.connection(pid) as conn:
            from app.knowledge.context import enrich_context
            # Uploading code/results can resolve earlier report references.
            for item in store.sources(conn, pid):
                if item['id'] == sid or item['kind'] == 'report':
                    enrich_context(conn, pid, item['id'])
        try:
            extraction.infer_cross_links(pid, sid, budget, lambda: _cancel_check(pid, rid))
        except model.ModelUnavailable as exc:
            warnings.append(str(exc))
        with store.connection(pid) as conn:
            extraction.connect_sources(conn, pid, sid)
            from app.knowledge.learning import add_prerequisites
            add_prerequisites(conn, pid, sid)
            status = "partial" if errors or warnings or "partial" in stages.values() else "succeeded"
            store.update_run(conn, pid, rid, status=status, progress=1, stages=stages, errors=errors, warnings=list(dict.fromkeys(warnings)), usage=budget.usage)
            from app.knowledge.unified import sync_research_facts, sync_legacy
            sync_research_facts(conn, pid)
            paper_uid = store.source(conn, pid, sid).get('paper_uid')
            if paper_uid:
                sync_legacy(conn, uid=paper_uid, project_id=pid)
    except Cancelled:
        with store.connection(pid) as conn:
            store.update_run(conn, pid, rid, status="cancelled", usage=budget.usage)
    except Exception as exc:
        with store.connection(pid) as conn:
            status = "partial" if stages.get("graph") == "done" else "failed"
            if stages["parse"] == "running":
                stages["parse"] = "failed"
            if stages["extract"] == "running":
                stages["extract"] = "failed"
            store.update_run(conn, pid, rid, status=status, errors=errors + [str(exc)[:500]], stages=stages, usage=budget.usage)


def recover():
    """Interrupted model work requires an explicit continue, never a paid replay."""
    with store.connection() as conn:
        rows = conn.execute("SELECT id,project_id FROM kw_runs WHERE status IN ('running','queued')").fetchall()
        for rid, pid in rows:
            store.update_run(conn, pid, rid, status="interrupted", errors=["服务已重启；已保存完成内容，选择继续分析恢复"])
        conn.execute("UPDATE kw_model_calls SET status='interrupted' WHERE status='running'")
        conn.execute("UPDATE kw_operations SET status='interrupted' WHERE status='running'")
