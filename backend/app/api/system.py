"""Local runtime diagnostics. Credentials and provider responses never leave here."""

import os
import json
import time
import ssl
from functools import lru_cache
from urllib.parse import urlparse
from datetime import UTC, datetime
from contextlib import closing
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Query

from app.config import get_settings
from app.db.sqlite import connect

router = APIRouter(prefix="/api/system", tags=["system"])


def database_status():
    try:
        with closing(connect()) as conn:
            conn.execute("SELECT 1").fetchone()
            count = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
        return {"status": "available", "paper_count": count}
    except Exception:
        return {"status": "unavailable", "reason": "本地数据库无法打开，请检查目录权限和磁盘空间"}


def graph_status():
    try:
        with closing(connect()) as conn:
            conn.execute('SELECT 1').fetchone()
        return {"status": "available", "backend": "sqlite-kw", "reason": "统一知识库按账号与研究空间隔离，图谱和审核无需 Neo4j"}
    except Exception:
        return {"status": "unavailable", "backend": "sqlite-kw", "reason": "当前账号的统一知识库无法读取"}


@lru_cache(maxsize=1)
def _tls_context():
    return ssl.create_default_context()


def parser_status():
    if get_settings().access_mode == "multiuser":
        return {"status": "fallback", "reason": "个人资料使用本地 PDF 文字解析，扫描件不执行 OCR", "fallback": "PyMuPDF"}
    try:
        url = f"{get_settings().grobid_base_url}/api/isalive"
        # Loading the Windows system certificate store can be slow. A local HTTP
        # health probe does not use TLS and must not block runtime diagnostics on it.
        verify = _tls_context() if urlparse(url).scheme == "https" else True
        with httpx.Client(timeout=1, verify=verify) as client:
            response = client.get(url)
            if response.status_code == 200:
                return {"status": "available", "fallback": "PyMuPDF"}
    except httpx.HTTPError:
        pass
    return {"status": "fallback", "reason": "使用本地 PDF 文本解析，扫描件不执行 OCR", "fallback": "PyMuPDF"}


@router.get("/status")
def runtime_status():
    from app.api.papers import _MAX_PDF_BYTES

    s = get_settings()
    database = database_status()
    graph = graph_status()
    parser = parser_status()
    # Keep the legacy GROBID probe contract; new source analysis uses the
    # installed local knowledge parser independently of that optional service.
    from importlib.util import find_spec
    artifacts = Path(__file__).resolve().parents[3] / '.tmp/models/docling/paperstride-models.json'
    parser['knowledge_backend'] = 'Docling' if s.knowledge_use_docling and find_spec('docling') is not None and artifacts.is_file() else 'PyMuPDF'
    from app.knowledge.model import available as knowledge_model_available
    model = {"status": "configured" if s.dashscope_api_key else "unconfigured",
             "research_enabled": s.research_model_enabled,
             'knowledge_enabled': bool(s.knowledge_model_enabled and not s.offline_mode),
             "reason": "配置状态不代表模型调用已经验证"}
    private = s.access_mode == "multiuser"
    result = {"contract_version": "runtime-v1", "mode": s.runtime_mode,
            "access_mode": s.access_mode,
            "runtime_id": "" if private else s.runtime_id, "pid": None if private else os.getpid(),
            "data_dir": "个人空间" if private else str(Path(s.data_dir).resolve()),
            "status": "unavailable" if database["status"] != "available" else
                      "ready" if graph["status"] == "available" and parser["status"] == "available" else "degraded",
            "services": {"database": database, "graph": graph, "parser": parser, "model": model},
            "limits": {"pdf_max_bytes": s.user_pdf_max_bytes if private else _MAX_PDF_BYTES,
                       "pdf_max_pages": s.user_pdf_max_pages if private else None,
                       "max_papers": s.user_max_papers if private else None,
                       "storage_max_bytes": s.user_storage_max_bytes if private else None},
            "capabilities": {"local_workspace": database["status"] == "available",
                             "automatic_actions": database["status"] == "available",
                             "graph": graph["status"] == "available",
                             'knowledge_model': knowledge_model_available(),
                             "research_model": bool(s.dashscope_api_key and s.research_model_enabled)}}
    if private:
        result.pop("pid")
        result.pop("runtime_id")
    return result


def _json(raw, default):
    try:
        return json.loads(raw) if raw else default
    except (ValueError, TypeError):
        return default


@router.get('/tasks')
def task_list(status: str | None = None, offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    with closing(connect()) as conn:
        sql = """WITH combined AS (
          SELECT 'legacy' AS kind,CAST(id AS TEXT) AS id,type,status,params_json,result_json,error,
                 NULL AS project_id,created_at,updated_at FROM tasks
          UNION ALL SELECT 'research',task_id,kind,CASE WHEN status='succeeded' THEN 'done' ELSE status END,
                 params_json,result_json,error_json,project_id,created_at,updated_at FROM research_async_tasks)
        """
        where = ' WHERE (? IS NULL OR t.status=?)'
        total = conn.execute(sql + 'SELECT COUNT(*) FROM combined t' + where, (status, status)).fetchone()[0]
        rows = conn.execute(sql + "SELECT t.*,c.phase,c.progress,c.started_at,c.heartbeat_at,c.deadline_at,c.error_code,c.cancel_requested "
                            "FROM combined t LEFT JOIN task_controls c ON c.task_key=t.kind||':'||t.id" + where +
                            ' ORDER BY t.created_at DESC,t.kind,t.id DESC LIMIT ? OFFSET ?', (status, status, limit, offset)).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            params = _json(item.pop('params_json'), {})
            result = _json(item.pop('result_json'), {})
            params = params if isinstance(params, dict) else {}
            result = result if isinstance(result, dict) else {}
            failure = _json(item['error'], None) if item['kind'] == 'research' else None
            item['error'] = failure.get('message') if isinstance(failure, dict) else item['error']
            item['error_code'] = item['error_code'] or (failure.get('code') if isinstance(failure, dict) else None)
            warnings = result.get('warnings', [])
            item['warnings'] = [warning for warning in warnings if isinstance(warning, (str,dict))] if isinstance(warnings, list) else []
            item['label'] = params.get('uid') or item['project_id'] or item['type']
            item['url'] = f"/research/{item['project_id']}" if item['project_id'] else f"/papers/{params['uid']}" if params.get('uid') else '/workflow'
            end = time.time()
            if item['status'] not in ('queued','running'):
                try:
                    parsed = datetime.fromisoformat(item['updated_at'])
                    end = (parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed).timestamp()
                except (ValueError, TypeError):
                    pass
            item['elapsed_seconds'] = max(0, int(end - item['started_at'])) if item['started_at'] else None
            item['overdue'] = bool(item['status'] == 'running' and item['deadline_at'] and time.time() > item['deadline_at'])
            item['can_cancel'] = item['status'] in ('queued','running')
            item['can_retry'] = item['status'] in ('failed','interrupted','cancelled') or bool(item['warnings'])
            items.append(item)
        return {'items': items, 'total': total, 'offset': offset, 'limit': limit}


@router.post('/tasks/{kind}/{ident}/cancel')
def cancel_task(kind: str, ident: str):
    from app.task_control import stop_task
    if kind not in ('legacy', 'research') or (kind == 'legacy' and not ident.isdecimal()):
        raise HTTPException(422, '任务标识不合法')
    with closing(connect()) as conn:
        try:
            return stop_task(conn, f'{kind}:{ident}')
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
