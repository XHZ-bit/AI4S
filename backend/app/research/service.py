"""Business orchestration and durable task handlers for Research Atlas."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from app.db import projects as store
from app.models.research import (
    CandidateBundle,
    ComparisonRequest,
    DecisionValidationRequest,
    ErrorDetail,
    ExtractionInput,
    FrozenDocument,
    GraphQuery,
    GraphProjectionStatus,
    GraphQueryResult,
    PlanBuildInput,
    PlanGenerateRequest,
    ProjectFactsResponse,
    ProjectSnapshot,
    ResearchDecisionCreate,
    SnapshotBuildInput,
    SnapshotCreateRequest,
    TaskKind,
    TaskStatus,
)


class CapabilityUnavailable(RuntimeError):
    def __init__(self, capability: str, message: str, *, temporary: bool = False):
        super().__init__(message)
        self.capability = capability
        self.temporary = temporary


# T0 intentionally leaves the external-model adapter unconfigured.  A deployment
# must explicitly supply an authorized provider; tests inject a local fake.
plan_suggestion_provider: Callable[[PlanBuildInput], dict] | None = None


def project_facts(
    conn, project_id: str, *, kind=None, status=None, paper_link_id=None
) -> ProjectFactsResponse:
    facts = store.list_facts(
        conn, project_id, kind=kind, status=status, paper_link_id=paper_link_id
    )
    return ProjectFactsResponse(
        methods=[f for f in facts if f.__class__.__name__ == "MethodCard"],
        experiment_settings=[
            f for f in facts if f.__class__.__name__ == "ExperimentSetting"
        ],
        measurements=[f for f in facts if f.__class__.__name__ == "Measurement"],
        evidence=store.list_evidence(conn, project_id),
    )


def compare_project_conditions(conn, project_id: str, request: ComparisonRequest):
    if request.project_id != project_id:
        raise store.InvalidStateError("比较请求属于其他项目")
    project = store.get_project(conn, project_id)
    if project is None:
        raise store.NotFoundError("项目不存在")
    store._check_version(project.version, request.project_version, "项目")
    if request.domain != project.domain:
        raise store.InvalidStateError("比较请求领域与项目领域不一致")
    facts = project_facts(conn, project_id)
    method_map = {f.id: f for f in facts.methods}
    setting_map = {f.id: f for f in facts.experiment_settings}
    measurement_map = {f.id: f for f in facts.measurements}
    for item in request.candidates:
        method = method_map.get(item.method_id)
        setting = setting_map.get(item.experiment_setting_id)
        if method is None or setting is None or setting.method_id != method.id:
            raise store.NotFoundError("比较候选引用了不存在或不匹配的事实")
        if any(
            mid not in measurement_map
            or measurement_map[mid].experiment_setting_id != setting.id
            for mid in item.measurement_ids
        ):
            raise store.NotFoundError("比较候选引用了不匹配的测量")
    selected_methods = {c.method_id for c in request.candidates}
    selected_settings = {c.experiment_setting_id for c in request.candidates}
    selected_measurements = {
        mid for c in request.candidates for mid in c.measurement_ids
    }
    bundle = CandidateBundle(
        project_id=project_id,
        paper_link_id="comparison-input",
        document_id="comparison-input",
        document_version="comparison-input",
        extraction_version="stored-facts",
        evidence=facts.evidence,
        methods=[method_map[x] for x in selected_methods],
        experiment_settings=[setting_map[x] for x in selected_settings],
        measurements=[measurement_map[x] for x in selected_measurements],
    )
    try:
        from app.research.comparison import compare_conditions
    except ImportError as exc:
        raise CapabilityUnavailable("comparison", "比较模块尚未接入") from exc
    try:
        return compare_conditions(request, bundle)
    except ValueError as exc:
        raise store.ValidationError(str(exc)) from exc
    except RuntimeError as exc:
        raise CapabilityUnavailable("comparison", str(exc), temporary=True) from exc


def create_decision(conn, project_id: str, request: ResearchDecisionCreate):
    project = store.get_project(conn, project_id)
    if project is None:
        raise store.NotFoundError("项目不存在")
    store._check_version(project.version, request.expected_project_version, "项目")
    facts = project_facts(conn, project_id)
    try:
        from app.research.decisions import validate_decision
    except ImportError as exc:
        raise CapabilityUnavailable(
            "decision_validation", "决策校验模块尚未接入"
        ) from exc
    result = validate_decision(
        DecisionValidationRequest(
            project=project,
            decision=request,
            methods=facts.methods,
            experiment_settings=facts.experiment_settings,
            measurements=facts.measurements,
        )
    )
    if not result.valid:
        raise store.ValidationError("; ".join(result.errors))
    return store.save_decision(conn, project_id, request)


def build_plan(conn, project_id: str, request: PlanGenerateRequest):
    project = store.get_project(conn, project_id)
    if project is None:
        raise store.NotFoundError("项目不存在")
    store._check_version(project.version, request.expected_project_version, "项目")
    decision = store.get_decision(conn, request.decision_id)
    if (
        not decision
        or decision.project_id != project_id
        or decision.version != request.decision_version
    ):
        raise store.NotFoundError("路线决策不存在或版本不匹配")
    facts = project_facts(conn, project_id)
    try:
        from app.research.planning import build_plan_draft
    except ImportError as exc:
        raise CapabilityUnavailable("plan_generation", "方案生成模块尚未接入") from exc
    provider = plan_suggestion_provider
    if provider is None:
        from app.config import get_settings
        if get_settings().research_model_enabled:
            from app.research.plan_provider import suggest_plan
            provider = suggest_plan
    if provider is None:
        raise CapabilityUnavailable(
            "plan_generation",
            "方案生成模型尚未授权接入；已保存方案仍可查看",
            temporary=False,
        )
    try:
        value = PlanBuildInput(
                project=project,
                decision=decision,
                methods=facts.methods,
                experiment_settings=facts.experiment_settings,
                measurements=facts.measurements,
                evidence=facts.evidence,
            )
        # Validate route/facts before any paid call. T3's standalone template
        # fallback remains available, but a production generation job must fail
        # if the provider fails or returns no usable suggestions.
        build_plan_draft(value)
        from app.research.plan_provider import validate_suggestions
        from app.research.model_runtime import ResearchModelError
        try:
            suggestions = validate_suggestions(provider(value.model_copy(deep=True)), value)
        except ResearchModelError:
            raise
        except Exception:
            raise ResearchModelError("model_provider_failed") from None
        plan = build_plan_draft(
            value, suggestion_provider=lambda _value: suggestions,
        )
        plan.title = f"[模型建议·待人工确认] {project.title}：首轮验证"
        return plan
    except RuntimeError as exc:
        from app.research.model_runtime import ResearchModelError
        if isinstance(exc, ResearchModelError):
            raise
        raise CapabilityUnavailable(
            "plan_generation", str(exc), temporary=True
        ) from exc


def _frozen_documents(conn, project_id: str) -> list[FrozenDocument]:
    values = []
    for link in store.list_paper_links(conn, project_id):
        if link.status.value != "active":
            continue
        if not link.linked_document_id or not link.linked_document_version:
            raise store.InvalidStateError(f"论文关联 {link.id} 尚未冻结文档版本")
        row = conn.execute(
            "SELECT content_hash FROM documents WHERE id=? AND paper_uid=?",
            (link.linked_document_id, link.paper_uid),
        ).fetchone()
        if not row:
            raise store.NotFoundError(f"论文关联 {link.id} 的文档不存在")
        values.append(
            FrozenDocument(
                paper_link_id=link.id,
                paper_uid=link.paper_uid,
                document_id=link.linked_document_id,
                document_version=link.linked_document_version,
                content_hash=row["content_hash"],
            )
        )
    if not values:
        raise store.InvalidStateError("创建快照前至少需要一篇带固定文档版本的论文")
    return values


def create_snapshot(conn, project_id: str, request: SnapshotCreateRequest):
    project = store.get_project(conn, project_id)
    if project is None:
        raise store.NotFoundError("项目不存在")
    store._check_version(project.version, request.expected_project_version, "项目")
    plan = store.get_plan_version(conn, request.plan_id, request.plan_version)
    if not plan or plan.project_id != project_id:
        raise store.NotFoundError("方案版本不存在")
    decisions = [
        d
        for d in store.list_decisions(conn, project_id)
        if d.status.value == "active"
        and d.selected_method_id == plan.selected_method_id
        and d.selected_experiment_setting_ids == plan.selected_experiment_setting_ids
    ]
    if not decisions:
        raise store.InvalidStateError("方案没有对应的有效路线决策")
    facts = project_facts(conn, project_id)
    documents = _frozen_documents(conn, project_id)
    try:
        from app.research.planning import build_snapshot_content
    except ImportError as exc:
        raise CapabilityUnavailable(
            "snapshot_build", "快照内容组装模块尚未接入"
        ) from exc
    try:
        snapshot = build_snapshot_content(
            SnapshotBuildInput(
                project=project,
                decision=decisions[-1],
                methods=facts.methods,
                experiment_settings=facts.experiment_settings,
                measurements=facts.measurements,
                evidence=facts.evidence,
                plan=plan,
                frozen_documents=documents,
            )
        )
    except ValueError as exc:
        raise store.ValidationError(str(exc)) from exc
    next_version = len(store.list_snapshots(conn, project_id)) + 1
    normalized = ProjectSnapshot.model_validate(
        snapshot.model_copy(
            update={
                "id": f"snapshot-{uuid4().hex}",
                "snapshot_version": next_version,
                "created_at": datetime.now(UTC),
            }
        ).model_dump()
    )
    return store.save_snapshot(conn, normalized)


def _document_input(
    conn, project_id: str, link_id: str, document_id: str
) -> ExtractionInput:
    project = store.get_project(conn, project_id)
    link = store.get_paper_link(conn, link_id)
    if project is None:
        raise store.NotFoundError("项目不存在")
    if not link or link.project_id != project_id or link.status.value != "active":
        raise store.NotFoundError("有效论文关联不存在")
    if link.linked_document_id != document_id or not link.linked_document_version:
        raise store.InvalidStateError("请求文档不是论文关联冻结的文档版本")
    row = conn.execute(
        "SELECT content_hash FROM documents WHERE id=? AND paper_uid=?",
        (document_id, link.paper_uid),
    ).fetchone()
    if not row:
        raise store.NotFoundError("文档不存在")
    passages = [
        dict(r)
        for r in conn.execute(
            "SELECT id,heading,text,page,ordinal,kind,metadata_json FROM passages WHERE document_id=? ORDER BY ordinal",
            (document_id,),
        ).fetchall()
    ]
    return ExtractionInput(
        project_id=project_id,
        paper_link=link,
        document=FrozenDocument(
            paper_link_id=link.id,
            paper_uid=link.paper_uid,
            document_id=document_id,
            document_version=link.linked_document_version,
            content_hash=row["content_hash"],
        ),
        passages=passages,
        domain=project.domain,
        domain_profile_version=project.domain_profile_version,
    )


def enqueue_research_task(
    conn,
    kind: TaskKind,
    project_id: str,
    params: dict,
    dispatcher: Callable[[str], None],
    *,
    retry_of=None,
):
    if dispatcher is None:
        raise CapabilityUnavailable("task_dispatch", "项目任务分发器尚未接入")
    task, created = store.get_or_create_task(
        conn, kind, project_id, params, retry_of=retry_of
    )
    if not created:
        return task
    try:
        dispatcher(task.id)
    except Exception as exc:
        store.update_task(
            conn,
            task.id,
            TaskStatus.FAILED,
            error=ErrorDetail(
                code="queue_unavailable", message=str(exc), retryable=True
            ),
        )
        raise CapabilityUnavailable(
            "task_dispatch", "项目任务队列不可用", temporary=True
        ) from exc
    return task


def enqueue_extraction(conn, project_id: str, link_id: str, request, dispatcher):
    project = store.get_project(conn, project_id)
    if project is None:
        raise store.NotFoundError("项目不存在")
    store._check_version(project.version, request.expected_project_version, "项目")
    _document_input(conn, project_id, link_id, request.document_id)
    return enqueue_research_task(
        conn,
        TaskKind.PROJECT_EXTRACTION,
        project_id,
        {
            "project_id": project_id,
            "link_id": link_id,
            "document_id": request.document_id,
        },
        dispatcher,
    )


def enqueue_plan_generation(
    conn, project_id: str, request: PlanGenerateRequest, dispatcher
):
    project = store.get_project(conn, project_id)
    if project is None:
        raise store.NotFoundError("项目不存在")
    store._check_version(project.version, request.expected_project_version, "项目")
    decision = store.get_decision(conn, request.decision_id)
    if (
        not decision
        or decision.project_id != project_id
        or decision.version != request.decision_version
    ):
        raise store.NotFoundError("路线决策不存在或版本不匹配")
    return enqueue_research_task(
        conn,
        TaskKind.PLAN_GENERATION,
        project_id,
        {"project_id": project_id, "request": request.model_dump(mode="json")},
        dispatcher,
    )


def _latest_projection_task_id(conn, project_id: str, snapshot_id: str) -> str | None:
    rows = conn.execute(
        "SELECT task_id,params_json FROM research_async_tasks "
        "WHERE kind=? AND project_id=? ORDER BY created_at DESC",
        (TaskKind.GRAPH_PROJECTION.value, project_id),
    ).fetchall()
    for row in rows:
        try:
            if json.loads(row["params_json"]).get("snapshot_id") == snapshot_id:
                return row["task_id"]
        except (TypeError, ValueError):
            continue
    return None


def graph_projection_status(
    conn, project_id: str, snapshot_id: str
) -> GraphProjectionStatus:
    snapshot = store.get_snapshot(conn, project_id, snapshot_id)
    if snapshot is None:
        raise store.NotFoundError("项目快照不存在")
    state = store.get_projection_state(conn, snapshot_id)
    if state is None or state["project_id"] != project_id:
        raise store.NotFoundError("图投影状态不存在")
    return GraphProjectionStatus(
        project_id=project_id,
        snapshot_id=snapshot_id,
        status=state["status"],
        task_id=_latest_projection_task_id(conn, project_id, snapshot_id),
        attempt_count=state["attempt_count"],
        last_error=state["last_error"],
        updated_at=state["updated_at"],
    )


def enqueue_graph_projection(
    conn,
    project_id: str,
    snapshot_id: str,
    dispatcher: Callable[[str], None],
    *,
    retry: bool = False,
):
    snapshot = store.get_snapshot(conn, project_id, snapshot_id)
    if snapshot is None:
        raise store.NotFoundError("项目快照不存在")
    state = store.get_projection_state(conn, snapshot_id)
    if state is None or state["project_id"] != project_id:
        raise store.NotFoundError("图投影状态不存在")
    if state["status"] == "succeeded":
        raise store.InvalidStateError("图投影已经同步成功")
    if retry and state["status"] == "running":
        raise store.InvalidStateError("图投影正在同步，不能重复重试")
    retry_of = _latest_projection_task_id(conn, project_id, snapshot_id) if retry else None
    if state["status"] == "failed":
        store.update_projection_state(conn, snapshot_id, "pending")
    try:
        return enqueue_research_task(
            conn,
            TaskKind.GRAPH_PROJECTION,
            project_id,
            {"snapshot_id": snapshot_id},
            dispatcher,
            retry_of=retry_of,
        )
    except Exception as exc:
        store.update_projection_state(conn, snapshot_id, "failed", error=str(exc))
        raise


def _task_failure(conn, task_id: str, exc: Exception):
    from app.research.model_runtime import ResearchModelError
    if isinstance(exc, ResearchModelError):
        code, retryable = exc.code, exc.retryable
    elif isinstance(exc, CapabilityUnavailable):
        code = "service_unavailable" if exc.temporary else "not_implemented"
        retryable = exc.temporary
    elif isinstance(exc, store.ProjectStoreError):
        code, retryable = exc.code, exc.retryable
    else:
        code, retryable = "task_failed", False
    return store.update_task(
        conn,
        task_id,
        TaskStatus.FAILED,
        error=ErrorDetail(code=code, message=str(exc), retryable=retryable),
    )


def run_extraction_task(conn, task_id: str):
    task = store.get_task(conn, task_id)
    if not task:
        raise store.NotFoundError("任务不存在")
    if task.status == TaskStatus.SUCCEEDED:
        return task
    params = store.get_task_params(conn, task_id)
    store.update_task(conn, task_id, TaskStatus.RUNNING, progress=0.05)
    try:
        value = _document_input(
            conn, params["project_id"], params["link_id"], params["document_id"]
        )
        try:
            from app.research.extraction import extract_candidates
        except ImportError as exc:
            raise CapabilityUnavailable("extraction", "候选抽取模块尚未接入") from exc
        bundle = extract_candidates(value)
        store.save_candidate_bundle(conn, bundle)
        return store.update_task(
            conn,
            task_id,
            TaskStatus.SUCCEEDED,
            progress=1.0,
            result={
                "project_id": bundle.project_id,
                "paper_link_id": bundle.paper_link_id,
                "method_count": len(bundle.methods),
                "experiment_setting_count": len(bundle.experiment_settings),
                "measurement_count": len(bundle.measurements),
                "warnings": bundle.warnings,
            },
        )
    except Exception as exc:
        return _task_failure(conn, task_id, exc)


def run_plan_generation_task(conn, task_id: str):
    task = store.get_task(conn, task_id)
    if not task:
        raise store.NotFoundError("任务不存在")
    if task.status == TaskStatus.SUCCEEDED:
        return task
    params = store.get_task_params(conn, task_id)
    store.update_task(conn, task_id, TaskStatus.RUNNING, progress=0.05)
    try:
        request = PlanGenerateRequest.model_validate(params["request"])
        plan = build_plan(conn, params["project_id"], request)
        return store.update_task(
            conn,
            task_id,
            TaskStatus.SUCCEEDED,
            progress=1.0,
            result={"plan": plan.model_dump(mode="json")},
        )
    except Exception as exc:
        return _task_failure(conn, task_id, exc)


def run_graph_projection(conn, snapshot_id: str):
    state = store.get_projection_state(conn, snapshot_id)
    if not state:
        raise store.NotFoundError("投影待同步记录不存在")
    snapshot = store.get_snapshot(conn, state["project_id"], snapshot_id)
    if not snapshot:
        raise store.NotFoundError("快照不存在")
    store.update_projection_state(conn, snapshot_id, "running")
    try:
        from app.research.graph_projection import build_graph_projection, project_graph

        result = project_graph(build_graph_projection(snapshot))
        store.update_projection_state(conn, snapshot_id, "succeeded")
        return result
    except Exception as exc:
        store.update_projection_state(conn, snapshot_id, "failed", error=str(exc))
        raise CapabilityUnavailable(
            "graph_projection", str(exc), temporary=True
        ) from exc


def query_graph(conn, query: GraphQuery) -> GraphQueryResult:
    """Read a successfully synchronized snapshot projection through T5 only."""

    if store.get_project(conn, query.project_id) is None:
        raise store.NotFoundError("项目不存在")
    snapshot = store.get_snapshot(conn, query.project_id, query.snapshot_id)
    if snapshot is None:
        raise store.NotFoundError("项目快照不存在")
    state = store.get_projection_state(conn, query.snapshot_id)
    if state is None or state["project_id"] != query.project_id:
        raise CapabilityUnavailable(
            "graph_query", "快照尚未创建图投影同步记录", temporary=True
        )
    if state["status"] != "succeeded":
        detail = f"图投影同步状态为 {state['status']}"
        if state["last_error"]:
            detail = f"{detail}: {state['last_error']}"
        raise CapabilityUnavailable("graph_query", detail, temporary=True)
    semantic_modes = {"dependency_path", "method_context", "impact_path"}
    if semantic_modes.intersection(query.kinds) and not query.node_ids:
        raise store.ValidationError("路径图查询必须提供 node_ids")
    try:
        from app.research.graph_queries import query_project_graph
    except ImportError as exc:
        raise CapabilityUnavailable("graph_query", "图查询模块尚未接入") from exc
    try:
        result = GraphQueryResult.model_validate(query_project_graph(query))
    except RuntimeError as exc:
        raise CapabilityUnavailable("graph_query", str(exc), temporary=True) from exc
    except (TypeError, ValueError) as exc:
        raise CapabilityUnavailable(
            "graph_query", "图查询服务返回了不符合契约的结果", temporary=True
        ) from exc
    if result.project_id != query.project_id or result.snapshot_id != query.snapshot_id:
        raise CapabilityUnavailable(
            "graph_query", "图查询结果不属于请求的项目快照", temporary=True
        )
    return result


def run_research_task(conn, task_id: str):
    task = store.get_task(conn, task_id)
    if not task:
        raise store.NotFoundError("任务不存在")
    if task.kind == TaskKind.PROJECT_EXTRACTION:
        return run_extraction_task(conn, task_id)
    if task.kind == TaskKind.PLAN_GENERATION:
        return run_plan_generation_task(conn, task_id)
    if task.kind == TaskKind.GRAPH_PROJECTION:
        params = store.get_task_params(conn, task_id)
        store.update_task(conn, task_id, TaskStatus.RUNNING, progress=0.05)
        try:
            result = run_graph_projection(conn, params["snapshot_id"])
            payload = (
                result.model_dump(mode="json")
                if hasattr(result, "model_dump")
                else result
            )
            return store.update_task(
                conn, task_id, TaskStatus.SUCCEEDED, progress=1.0, result=payload
            )
        except Exception as exc:
            return _task_failure(conn, task_id, exc)
    raise store.InvalidStateError("不支持的项目任务类型")


def snapshot_json(snapshot: ProjectSnapshot) -> bytes:
    return json.dumps(
        snapshot.model_dump(mode="json"), ensure_ascii=False, indent=2
    ).encode()


def snapshot_markdown(snapshot: ProjectSnapshot) -> bytes:
    plan = snapshot.plan
    lines = [
        f"# {plan.title}",
        "",
        f"- 项目：`{snapshot.project_id}`",
        f"- 快照：`{snapshot.id}`（v{snapshot.snapshot_version}）",
        f"- 方案版本：v{plan.version}",
        f"- 复核状态：`{snapshot.review_status.value}`",
        "",
        "## 目标",
        "",
        plan.objective,
    ]
    if plan.hypothesis:
        lines += ["", "## 假设", "", plan.hypothesis]
    if plan.unknowns:
        lines += ["", "## 未知项", ""] + [f"- {x}" for x in plan.unknowns]
    if plan.steps:
        lines += ["", "## 验证步骤", ""]
        for index, step in enumerate(plan.steps, 1):
            lines += [f"### {index}. {step.title}", "", step.purpose, ""] + [
                f"- {x}" for x in step.procedure
            ]
    if snapshot.review_reasons:
        lines += ["", "## 复核原因", ""] + [f"- {x}" for x in snapshot.review_reasons]
    lines += ["", "## 冻结来源", ""] + [
        f"- `{d.paper_uid}` / `{d.document_id}` / `{d.document_version}`"
        for d in snapshot.frozen_documents
    ]
    return "\n".join(lines).encode()
