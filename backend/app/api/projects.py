"""HTTP adapter for the frozen Research Atlas project API."""

import logging
from contextlib import closing
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Response

from app.db import projects as store
from app.db.sqlite import connect
from app.models.research import (
    AsyncTask,
    ComparisonRequest,
    ComparisonResult,
    DecisionListResponse,
    DomainId,
    ExtractionStartRequest,
    ExperimentSetting,
    GraphQuery,
    GraphQueryResult,
    GraphProjectionStatus,
    Measurement,
    MethodCard,
    PaperLink,
    PaperLinkCreate,
    PaperLinkListResponse,
    PaperLinkPatch,
    PlanGenerateRequest,
    PlanListResponse,
    PlanSaveRequest,
    ProjectFactsResponse,
    ProjectListResponse,
    ProjectSnapshot,
    ProjectStatus,
    ResearchDecision,
    ResearchDecisionCreate,
    ResearchProject,
    ResearchProjectCreate,
    ResearchProjectPatch,
    RecordStatus,
    SnapshotCreateRequest,
    SnapshotListResponse,
    StatusTransitionRequest,
    TaskStatus,
    ValidationPlan,
)
from app.research import service


router = APIRouter(prefix="/api/projects", tags=["projects"])
logger = logging.getLogger(__name__)


def _connect():
    conn = connect()
    store.init_research_schema(conn)
    return conn


def _task_dispatcher():
    try:
        from app.jobs import enqueue_research_task
    except ImportError as exc:
        raise service.CapabilityUnavailable(
            "task_dispatch", "项目任务分发器尚未接入"
        ) from exc
    return enqueue_research_task


def _error(status, code, message, *, retryable=False, current_version=None):
    raise HTTPException(
        status_code=status,
        detail={
            "code": code,
            "message": message,
            "retryable": retryable,
            "fields": {},
            "current_version": current_version
            if current_version and current_version > 0
            else None,
            "request_id": None,
        },
    )


def _translate(exc: Exception):
    if isinstance(exc, store.NotFoundError):
        _error(404, exc.code, str(exc))
    if isinstance(exc, store.VersionConflictError):
        _error(
            409, exc.code, str(exc), retryable=True, current_version=exc.current_version
        )
    if isinstance(exc, store.InvalidStateError):
        _error(409, exc.code, str(exc), current_version=exc.current_version)
    if isinstance(exc, store.ProjectStoreError):
        _error(422, exc.code, str(exc), current_version=exc.current_version)
    if isinstance(exc, service.CapabilityUnavailable):
        status = 503 if exc.temporary else 501
        if not exc.temporary:
            code = "not_implemented"
        elif exc.capability == "comparison":
            code = "model_unavailable"
        elif exc.capability in {
            "extraction",
            "plan_generation",
            "decision_validation",
        }:
            code = "model_unavailable"
        elif exc.capability.startswith("graph"):
            code = "graph_unavailable"
        else:
            code = "not_implemented"
        _error(status, code, str(exc), retryable=exc.temporary)
    raise exc


@router.post("", status_code=201, response_model=ResearchProject)
def create_project(request: ResearchProjectCreate):
    with closing(_connect()) as conn:
        try:
            return store.create_project(conn, request)
        except Exception as exc:
            _translate(exc)


@router.get("", response_model=ProjectListResponse)
def projects(
    status: ProjectStatus | None = None,
    domain: DomainId | None = None,
    cursor: str | None = None,
    limit: int = Query(50, ge=1, le=200),
):
    with closing(_connect()) as conn:
        try:
            items, next_cursor = store.list_projects(
                conn,
                status=status.value if status else None,
                domain=domain.value if domain else None,
                cursor=cursor,
                limit=limit,
            )
            return ProjectListResponse(items=items, next_cursor=next_cursor)
        except Exception as exc:
            _translate(exc)


@router.get("/{project_id}", response_model=ResearchProject)
def project(project_id: str):
    with closing(_connect()) as conn:
        value = store.get_project(conn, project_id)
        if value is None:
            _error(404, "not_found", "项目不存在")
        return value


@router.patch("/{project_id}", response_model=ResearchProject)
def patch_project(project_id: str, request: ResearchProjectPatch):
    with closing(_connect()) as conn:
        try:
            return store.update_project(conn, project_id, request)
        except Exception as exc:
            _translate(exc)


@router.get("/{project_id}/papers", response_model=PaperLinkListResponse)
def papers(project_id: str):
    with closing(_connect()) as conn:
        try:
            return PaperLinkListResponse(items=store.list_paper_links(conn, project_id))
        except Exception as exc:
            _translate(exc)


@router.post("/{project_id}/papers", status_code=201, response_model=PaperLink)
def add_paper(project_id: str, request: PaperLinkCreate):
    with closing(_connect()) as conn:
        try:
            return store.link_paper(
                conn, project_id, request.expected_project_version, request
            )
        except Exception as exc:
            _translate(exc)


@router.patch("/{project_id}/papers/{link_id}", response_model=PaperLink)
def patch_paper(project_id: str, link_id: str, request: PaperLinkPatch):
    with closing(_connect()) as conn:
        try:
            return store.update_paper_link(conn, project_id, link_id, request)
        except Exception as exc:
            _translate(exc)


@router.post(
    "/{project_id}/papers/{link_id}/extractions",
    status_code=202,
    response_model=AsyncTask,
)
def start_extraction(project_id: str, link_id: str, request: ExtractionStartRequest):
    with closing(_connect()) as conn:
        try:
            return service.enqueue_extraction(
                conn, project_id, link_id, request, _task_dispatcher()
            )
        except Exception as exc:
            _translate(exc)


@router.get("/{project_id}/facts", response_model=ProjectFactsResponse)
def facts(
    project_id: str,
    kind: Literal["method", "experiment_setting", "measurement"] | None = None,
    status: RecordStatus | None = None,
    paper_link_id: str | None = None,
):
    with closing(_connect()) as conn:
        try:
            return service.project_facts(
                conn,
                project_id,
                kind=kind,
                status=status.value if status else None,
                paper_link_id=paper_link_id,
            )
        except Exception as exc:
            _translate(exc)


@router.patch(
    "/{project_id}/facts/{fact_id}/status",
    response_model=MethodCard | ExperimentSetting | Measurement,
)
def patch_fact_status(project_id: str, fact_id: str, request: StatusTransitionRequest):
    with closing(_connect()) as conn:
        try:
            return store.transition_fact(conn, project_id, fact_id, request)
        except Exception as exc:
            _translate(exc)


@router.post("/{project_id}/comparisons", response_model=ComparisonResult)
def compare(project_id: str, request: ComparisonRequest):
    with closing(_connect()) as conn:
        try:
            return service.compare_project_conditions(conn, project_id, request)
        except Exception as exc:
            _translate(exc)


@router.get("/{project_id}/decisions", response_model=DecisionListResponse)
def decisions(project_id: str):
    with closing(_connect()) as conn:
        try:
            return DecisionListResponse(items=store.list_decisions(conn, project_id))
        except Exception as exc:
            _translate(exc)


@router.post(
    "/{project_id}/decisions", status_code=201, response_model=ResearchDecision
)
def add_decision(project_id: str, request: ResearchDecisionCreate):
    with closing(_connect()) as conn:
        try:
            return service.create_decision(conn, project_id, request)
        except Exception as exc:
            _translate(exc)


@router.post("/{project_id}/plans/generate", status_code=202, response_model=AsyncTask)
def generate_plan(project_id: str, request: PlanGenerateRequest):
    with closing(_connect()) as conn:
        try:
            return service.enqueue_plan_generation(
                conn, project_id, request, _task_dispatcher()
            )
        except Exception as exc:
            _translate(exc)


@router.get("/{project_id}/plans", response_model=PlanListResponse)
def plans(project_id: str):
    with closing(_connect()) as conn:
        try:
            return PlanListResponse(items=store.list_plans(conn, project_id))
        except Exception as exc:
            _translate(exc)


@router.put("/{project_id}/plans/{plan_id}", response_model=ValidationPlan)
def put_plan(project_id: str, plan_id: str, request: PlanSaveRequest):
    with closing(_connect()) as conn:
        try:
            if request.plan.id is not None and request.plan.id != plan_id:
                raise store.InvalidStateError("URL 与方案 ID 不一致")
            normalized = request.model_copy(
                update={"plan": request.plan.model_copy(update={"id": plan_id})}
            )
            return store.save_plan(conn, project_id, normalized)
        except Exception as exc:
            _translate(exc)


@router.post("/{project_id}/snapshots", status_code=201, response_model=ProjectSnapshot)
def add_snapshot(project_id: str, request: SnapshotCreateRequest):
    with closing(_connect()) as conn:
        try:
            value = service.create_snapshot(conn, project_id, request)
            try:
                service.enqueue_graph_projection(
                    conn, project_id, value.id, _task_dispatcher()
                )
            except Exception as exc:
                # The immutable SQLite snapshot is already committed.  Preserve it
                # and expose the explicit failed projection state for retry.
                logger.warning("Could not enqueue graph projection %s: %s", value.id, exc)
            return value
        except Exception as exc:
            _translate(exc)


@router.get("/{project_id}/snapshots", response_model=SnapshotListResponse)
def snapshots(project_id: str):
    with closing(_connect()) as conn:
        try:
            return SnapshotListResponse(items=store.list_snapshots(conn, project_id))
        except Exception as exc:
            _translate(exc)


@router.get("/{project_id}/snapshots/{snapshot_id}", response_model=ProjectSnapshot)
def snapshot(project_id: str, snapshot_id: str):
    with closing(_connect()) as conn:
        value = store.get_snapshot(conn, project_id, snapshot_id)
        if value is None:
            _error(404, "not_found", "快照不存在")
        return value


@router.get("/{project_id}/snapshots/{snapshot_id}/export")
def export_snapshot(
    project_id: str, snapshot_id: str, format: Literal["markdown", "json"] = "markdown"
):
    with closing(_connect()) as conn:
        value = store.get_snapshot(conn, project_id, snapshot_id)
        if value is None:
            _error(404, "not_found", "快照不存在")
        content = (
            service.snapshot_json(value)
            if format == "json"
            else service.snapshot_markdown(value)
        )
        suffix = "json" if format == "json" else "md"
        media = (
            "application/json" if format == "json" else "text/markdown; charset=utf-8"
        )
        return Response(
            content=content,
            media_type=media,
            headers={
                "Content-Disposition": f'attachment; filename="{snapshot_id}.{suffix}"'
            },
        )


@router.get(
    "/{project_id}/snapshots/{snapshot_id}/projection",
    response_model=GraphProjectionStatus,
)
def projection_status(project_id: str, snapshot_id: str):
    with closing(_connect()) as conn:
        try:
            return service.graph_projection_status(conn, project_id, snapshot_id)
        except Exception as exc:
            _translate(exc)


@router.post(
    "/{project_id}/snapshots/{snapshot_id}/projection/retry",
    status_code=202,
    response_model=AsyncTask,
)
def retry_projection(project_id: str, snapshot_id: str):
    with closing(_connect()) as conn:
        try:
            return service.enqueue_graph_projection(
                conn,
                project_id,
                snapshot_id,
                _task_dispatcher(),
                retry=True,
            )
        except Exception as exc:
            _translate(exc)


@router.get("/tasks/{task_id}", response_model=AsyncTask)
def task(task_id: str):
    with closing(_connect()) as conn:
        value = store.get_task(conn, task_id)
        if value is None:
            _error(404, "not_found", "任务不存在")
        return value


@router.post("/tasks/{task_id}/retry", status_code=202, response_model=AsyncTask)
def retry_task(task_id: str):
    with closing(_connect()) as conn:
        try:
            prior = store.get_task(conn, task_id)
            if prior is None:
                raise store.NotFoundError("任务不存在")
            if prior.status not in {TaskStatus.FAILED, TaskStatus.INTERRUPTED}:
                raise store.InvalidStateError("只能重试失败或中断的任务")
            return service.enqueue_research_task(
                conn,
                prior.kind,
                prior.project_id,
                store.get_task_params(conn, task_id),
                _task_dispatcher(),
                retry_of=task_id,
            )
        except Exception as exc:
            _translate(exc)


@router.get("/{project_id}/graph", response_model=GraphQueryResult)
def graph(
    project_id: str,
    snapshot_id: str,
    node_ids: list[str] = Query(default=[]),
    kinds: list[str] = Query(default=[]),
    limit: int = Query(default=200, ge=1, le=1000),
):
    with closing(_connect()) as conn:
        try:
            return service.query_graph(
                conn,
                GraphQuery(
                    project_id=project_id,
                    snapshot_id=snapshot_id,
                    node_ids=node_ids,
                    kinds=kinds,
                    limit=limit,
                ),
            )
        except Exception as exc:
            _translate(exc)
