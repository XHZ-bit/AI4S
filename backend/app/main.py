import logging
from contextlib import asynccontextmanager, nullcontext
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from neo4j.exceptions import AuthError, ServiceUnavailable, SessionExpired

from app.api.cases import router as cases_router
from app.api.learning import router as learning_router
from app.api.curation import router as curation_router
from app.api.quality_edit import router as quality_edit_router
from app.api.collect import router as collect_router
from app.api.extract import router as extract_router
from app.api.graph import router as graph_router
from app.api.papers import router as papers_router
from app.api.review import router as review_router
from app.api.roadmap import router as roadmap_router
from app.api.search import router as search_router
from app.api.projects import router as projects_router
from app.api.assistant import router as assistant_router
from app.api.workflow import router as workflow_router
from app.api.system import router as system_router, database_status
from app.api.actions import router as actions_router
from app.api.accounts import router as accounts_router
from app.api.library import router as library_router
from app.api.reading_position import router as reading_position_router
from app.api.preferences import router as preferences_router
from app.api.tutoring import router as tutoring_router
from app.api.workbench import router as workbench_router
from app.api.stride import router as stride_router
from app.api.stride_learning import router as stride_learning_router
from app.api.stride_graph import router as stride_graph_router
from app.api.topic_exploration import router as topic_exploration_router
from app.api.knowledge import router as knowledge_router
from app.api.knowledge_practice import router as knowledge_practice_router
from app.api.knowledge_experience import router as knowledge_experience_router
from app.api.knowledge_global import router as knowledge_global_router
from app.db.neo4j_client import close_driver
from app.db.sqlite import (
    connect,
    reset_research_running_tasks,
    reset_running_tasks,
)
from app.tasks import shutdown_executor
from app.config import get_settings
from app.tenancy import user_scope
from app.access import AccountBoundary

logger = logging.getLogger(__name__)


def recover_workspace():
    conn = connect()
    try:
        stale = reset_running_tasks(conn)
        if stale:
            logger.warning("reset %s stale running task(s) from previous run", stale)
        research_stale = reset_research_running_tasks(conn)
        if research_stale:
            logger.warning(
                "interrupted %s stale research task(s) from previous run",
                research_stale,
            )
        from app.jobs import recover_safe_queue
        recover_safe_queue(conn)
        from app.knowledge.service import recover as recover_knowledge
        recover_knowledge()
    finally:
        conn.close()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    from app.storage_lock import data_writer
    settings = get_settings()
    multiuser = settings.access_mode == "multiuser"
    lease = data_writer(Path(settings.data_dir)) if multiuser else nullcontext()
    with lease:
        try:
            if multiuser:
                from app.accounts import initialize, list_users
                initialize()
                for user in list_users():
                    existing = Path(settings.data_dir) / "users" / user["id"] / "atlas.db"
                    if existing.is_file():
                        with user_scope(user):
                            recover_workspace()
            else:
                recover_workspace()
                if (Path(settings.data_dir) / "identity.db").is_file():
                    from app.accounts import list_users
                    for user in list_users():
                        if (Path(settings.data_dir) / "users" / user["id"] / "atlas.db").is_file():
                            with user_scope(user):
                                recover_workspace()
            yield
        finally:
            close_driver()
            # Keep the backup barrier until every background writer has finished.
            shutdown_executor(wait=multiuser)
            from app.llm.client import close_client
            close_client()


app = FastAPI(title="PaperStride", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AccountBoundary)

app.include_router(cases_router)
app.include_router(learning_router)
app.include_router(curation_router)
app.include_router(quality_edit_router)
app.include_router(collect_router)
app.include_router(extract_router)
app.include_router(graph_router)
app.include_router(papers_router)
app.include_router(review_router)
app.include_router(search_router)
app.include_router(roadmap_router)
app.include_router(projects_router)
app.include_router(assistant_router)
app.include_router(workflow_router)
app.include_router(system_router)
app.include_router(actions_router)
app.include_router(accounts_router)
app.include_router(library_router)
app.include_router(reading_position_router)
app.include_router(preferences_router)
app.include_router(tutoring_router)


async def graph_unavailable(_request: Request, _exc: Exception):
    return JSONResponse(
        status_code=503,
        content={"detail": "图服务暂不可用，请检查 Neo4j 服务与连接配置后重试；已保存的论文、课题和方案仍可使用"},
    )


for graph_error in (ServiceUnavailable, SessionExpired, AuthError):
    app.add_exception_handler(graph_error, graph_unavailable)


@app.exception_handler(RequestValidationError)
async def project_validation_error(request: Request, exc: RequestValidationError):
    if not request.url.path.startswith("/api/projects"):
        return await request_validation_exception_handler(request, exc)
    fields = {
        ".".join(str(part) for part in error.get("loc", ()) if part != "body"):
        error.get("msg", "请求字段不合法")
        for error in exc.errors()
    }
    return JSONResponse(
        status_code=422,
        content={
            "detail": {
                "code": "validation_error",
                "message": "请求字段校验失败",
                "retryable": False,
                "fields": fields,
                "current_version": None,
                "request_id": None,
            }
        },
    )


@app.get("/health")
def health() -> dict:
    if get_settings().access_mode == "multiuser":
        from app.accounts import initialize
        try:
            initialize()
        except Exception:
            return JSONResponse(status_code=503, content={"status": "unavailable"})
        return {"status": "ok"}
    database = database_status()
    if database["status"] != "available":
        return JSONResponse(status_code=503, content={"status": "unavailable", "database": database})
    return {"status": "ok"}

app.include_router(workbench_router)

app.include_router(stride_router)
app.include_router(stride_learning_router)

app.include_router(stride_graph_router)

app.include_router(topic_exploration_router)

app.include_router(knowledge_router)
app.include_router(knowledge_practice_router)
app.include_router(knowledge_experience_router)
app.include_router(knowledge_global_router)
