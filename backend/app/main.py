import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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
from app.db.neo4j_client import close_driver, ensure_constraints
from app.db.sqlite import (
    connect,
    reset_research_running_tasks,
    reset_running_tasks,
)
from app.tasks import shutdown_executor

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
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
    finally:
        conn.close()
    try:
        ensure_constraints()
    except Exception as exc:
        logger.warning("Neo4j constraint initialization failed: %s", exc)
    yield
    close_driver()
    shutdown_executor(wait=False)


app = FastAPI(title="Research Atlas", version="0.1.0", lifespan=lifespan)

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
    return {"status": "ok"}
