"""Additive SQLite persistence for the Research Atlas project workflow."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import Iterable
from uuid import uuid4

from app.models.research import (
    ALLOWED_RECORD_STATUS_TRANSITIONS,
    AsyncTask,
    CandidateBundle,
    DecisionStatus,
    DOMAIN_PROFILES,
    ErrorDetail,
    EvidenceRef,
    ExperimentSetting,
    MethodCard,
    Measurement,
    PaperLink,
    PaperLinkCreate,
    PaperLinkPatch,
    PlanSaveRequest,
    PlanStatus,
    ProjectSnapshot,
    RecordStatus,
    ResearchDecision,
    ResearchDecisionCreate,
    ResearchProject,
    ResearchProjectCreate,
    ResearchProjectPatch,
    ReviewStatus,
    StatusTransitionRequest,
    TaskKind,
    TaskStatus,
    ValidationPlan,
    VersionRef,
)


SCHEMA = """
CREATE TABLE IF NOT EXISTS research_project_versions (
 project_id TEXT NOT NULL, version INTEGER NOT NULL, payload_json TEXT NOT NULL,
 created_at TEXT NOT NULL, PRIMARY KEY(project_id, version));
CREATE TABLE IF NOT EXISTS research_paper_link_versions (
 link_id TEXT NOT NULL, project_id TEXT NOT NULL, version INTEGER NOT NULL,
 paper_uid TEXT NOT NULL, status TEXT NOT NULL, payload_json TEXT NOT NULL,
 created_at TEXT NOT NULL, PRIMARY KEY(link_id, version));
CREATE INDEX IF NOT EXISTS idx_research_links_project
 ON research_paper_link_versions(project_id, link_id, version);
CREATE TABLE IF NOT EXISTS research_evidence (
 evidence_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, paper_link_id TEXT NOT NULL,
 payload_json TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS research_fact_versions (
 fact_id TEXT NOT NULL, project_id TEXT NOT NULL, fact_kind TEXT NOT NULL,
 version INTEGER NOT NULL, status TEXT NOT NULL, payload_json TEXT NOT NULL,
 created_at TEXT NOT NULL, PRIMARY KEY(fact_id, version));
CREATE INDEX IF NOT EXISTS idx_research_facts_project
 ON research_fact_versions(project_id, fact_kind, fact_id, version);
CREATE TABLE IF NOT EXISTS research_fact_audit (
 id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL, fact_id TEXT NOT NULL,
 from_version INTEGER NOT NULL, to_version INTEGER NOT NULL, action TEXT NOT NULL,
 actor TEXT NOT NULL, reason TEXT NOT NULL, before_json TEXT NOT NULL,
 after_json TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS research_decision_versions (
 decision_id TEXT NOT NULL, project_id TEXT NOT NULL, version INTEGER NOT NULL,
 status TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL,
 PRIMARY KEY(decision_id, version));
CREATE TABLE IF NOT EXISTS research_plan_versions (
 plan_id TEXT NOT NULL, project_id TEXT NOT NULL, version INTEGER NOT NULL,
 status TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL,
 PRIMARY KEY(plan_id, version));
CREATE TABLE IF NOT EXISTS research_snapshots (
 snapshot_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, snapshot_version INTEGER NOT NULL,
 payload_json TEXT NOT NULL, review_status TEXT NOT NULL,
 review_reasons_json TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL,
 UNIQUE(project_id, snapshot_version));
CREATE TABLE IF NOT EXISTS research_snapshot_dependencies (
 snapshot_id TEXT NOT NULL, ref_type TEXT NOT NULL, ref_id TEXT NOT NULL,
 ref_version INTEGER NOT NULL DEFAULT -1,
 PRIMARY KEY(snapshot_id, ref_type, ref_id, ref_version));
CREATE INDEX IF NOT EXISTS idx_research_snapshot_refs
 ON research_snapshot_dependencies(ref_type, ref_id);
CREATE TABLE IF NOT EXISTS research_async_tasks (
 task_id TEXT PRIMARY KEY, kind TEXT NOT NULL, status TEXT NOT NULL,
 project_id TEXT NOT NULL, progress REAL, params_json TEXT NOT NULL DEFAULT '{}',
 result_json TEXT, error_json TEXT, retry_of TEXT, created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_research_tasks_active_request
 ON research_async_tasks(kind, project_id, params_json, status);
CREATE TABLE IF NOT EXISTS research_projection_outbox (
 snapshot_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending', attempt_count INTEGER NOT NULL DEFAULT 0,
 last_error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_research_projection_pending
 ON research_projection_outbox(status, project_id, snapshot_id);
"""


class ProjectStoreError(Exception):
    code = "validation_error"
    retryable = False

    def __init__(self, message: str, *, current_version: int | None = None):
        super().__init__(message)
        self.current_version = current_version


class NotFoundError(ProjectStoreError):
    code = "not_found"


class VersionConflictError(ProjectStoreError):
    code = "version_conflict"
    retryable = True


class InvalidStateError(ProjectStoreError):
    code = "invalid_status_transition"


class ValidationError(ProjectStoreError):
    code = "validation_error"


def init_research_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def _now() -> datetime:
    return datetime.now(UTC)


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def _dump(model) -> str:
    return model.model_dump_json()


def _begin(conn: sqlite3.Connection) -> None:
    conn.execute("BEGIN IMMEDIATE")


def _latest_row(conn, table: str, id_column: str, value: str):
    allowed = {
        ("research_project_versions", "project_id"),
        ("research_paper_link_versions", "link_id"),
        ("research_fact_versions", "fact_id"),
        ("research_decision_versions", "decision_id"),
        ("research_plan_versions", "plan_id"),
    }
    if (table, id_column) not in allowed:
        raise ValueError("unsupported version table")
    return conn.execute(
        f"SELECT * FROM {table} WHERE {id_column}=? ORDER BY version DESC LIMIT 1",
        (value,),
    ).fetchone()


def _check_version(actual: int, expected: int, label: str) -> None:
    if actual != expected:
        raise VersionConflictError(f"{label}已更新，请重新加载", current_version=actual)


def get_project(conn, project_id: str) -> ResearchProject | None:
    row = _latest_row(conn, "research_project_versions", "project_id", project_id)
    return ResearchProject.model_validate_json(row["payload_json"]) if row else None


def _require_project(conn, project_id: str) -> ResearchProject:
    project = get_project(conn, project_id)
    if project is None:
        raise NotFoundError("项目不存在")
    return project


def _insert_project(conn, project: ResearchProject) -> None:
    conn.execute(
        "INSERT INTO research_project_versions(project_id,version,payload_json,created_at) VALUES(?,?,?,?)",
        (project.id, project.version, _dump(project), project.updated_at.isoformat()),
    )


def create_project(conn, request: ResearchProjectCreate) -> ResearchProject:
    now = _now()
    project = ResearchProject(
        id=_new_id("project"),
        version=1,
        title=request.title,
        research_question=request.research_question,
        domain=request.domain,
        domain_profile_version=DOMAIN_PROFILES[request.domain].version,
        constraints=request.constraints,
        created_at=now,
        updated_at=now,
    )
    _begin(conn)
    try:
        _insert_project(conn, project)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return project


def list_projects(conn, *, status=None, domain=None, cursor=None, limit=50):
    if not 1 <= limit <= 200:
        raise ProjectStoreError("limit 必须在 1 到 200 之间")
    rows = conn.execute(
        """SELECT p.payload_json FROM research_project_versions p
        JOIN (SELECT project_id,MAX(version) version FROM research_project_versions GROUP BY project_id) x
          ON x.project_id=p.project_id AND x.version=p.version
        WHERE (? IS NULL OR json_extract(p.payload_json,'$.status')=?)
          AND (? IS NULL OR json_extract(p.payload_json,'$.domain')=?)
          AND (? IS NULL OR p.project_id>?) ORDER BY p.project_id LIMIT ?""",
        (status, status, domain, domain, cursor, cursor, limit + 1),
    ).fetchall()
    items = [
        ResearchProject.model_validate_json(r["payload_json"]) for r in rows[:limit]
    ]
    return items, items[-1].id if len(rows) > limit and items else None


def update_project(
    conn, project_id: str, request: ResearchProjectPatch
) -> ResearchProject:
    _begin(conn)
    try:
        current = _require_project(conn, project_id)
        _check_version(current.version, request.expected_version, "项目")
        changes = request.model_dump(exclude={"expected_version"}, exclude_none=True)
        if (
            request.constraints is not None
            and request.constraints.version != current.constraints.version + 1
        ):
            raise ProjectStoreError("约束更新必须将 constraints.version 递增 1")
        if request.constraints is not None:
            changes["constraints"] = request.constraints
        updated = ResearchProject.model_validate(
            current.model_copy(
                update={**changes, "version": current.version + 1, "updated_at": _now()}
            ).model_dump()
        )
        _insert_project(conn, updated)
        reasons = []
        if "constraints" in changes:
            reasons.append("项目约束已更新")
        if "research_question" in changes:
            reasons.append("研究问题已更新")
        _mark_snapshots(
            conn, [VersionRef(id=project_id, version=current.version)], reasons
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return updated


def _latest_document(conn, paper_uid: str):
    return conn.execute(
        "SELECT id,content_hash FROM documents WHERE paper_uid=? ORDER BY created_at DESC,rowid DESC LIMIT 1",
        (paper_uid,),
    ).fetchone()


def get_paper_link(conn, link_id: str) -> PaperLink | None:
    row = _latest_row(conn, "research_paper_link_versions", "link_id", link_id)
    return PaperLink.model_validate_json(row["payload_json"]) if row else None


def link_paper(
    conn, project_id: str, expected_project_version: int, request: PaperLinkCreate
) -> PaperLink:
    if request.expected_project_version != expected_project_version:
        raise ProjectStoreError("请求中的项目版本不一致")
    _begin(conn)
    try:
        project = _require_project(conn, project_id)
        _check_version(project.version, expected_project_version, "项目")
        if (
            conn.execute(
                "SELECT 1 FROM papers WHERE uid=?", (request.paper_uid,)
            ).fetchone()
            is None
        ):
            raise NotFoundError("论文不存在")
        row = conn.execute(
            """SELECT p.payload_json FROM research_paper_link_versions p
            JOIN (SELECT link_id,MAX(version) version FROM research_paper_link_versions
                  WHERE project_id=? GROUP BY link_id) x
              ON x.link_id=p.link_id AND x.version=p.version
            WHERE p.project_id=? AND p.paper_uid=? AND p.status='active' LIMIT 1""",
            (project_id, project_id, request.paper_uid),
        ).fetchone()
        if row:
            existing = PaperLink.model_validate_json(row["payload_json"])
            if existing.role == request.role and existing.note == request.note:
                conn.rollback()
                return existing
            raise InvalidStateError("该论文已关联；请使用 PATCH 修改角色或备注")
        doc = _latest_document(conn, request.paper_uid)
        now = _now()
        link = PaperLink(
            id=_new_id("paper-link"),
            project_id=project_id,
            version=1,
            paper_uid=request.paper_uid,
            role=request.role,
            note=request.note,
            linked_document_id=doc["id"] if doc else None,
            linked_document_version=f"sha256:{doc['content_hash']}" if doc else None,
            created_at=now,
            updated_at=now,
        )
        conn.execute(
            "INSERT INTO research_paper_link_versions(link_id,project_id,version,paper_uid,status,payload_json,created_at) VALUES(?,?,?,?,?,?,?)",
            (
                link.id,
                project_id,
                1,
                link.paper_uid,
                link.status.value,
                _dump(link),
                now.isoformat(),
            ),
        )
        _insert_project(
            conn,
            ResearchProject.model_validate(
                project.model_copy(
                    update={"version": project.version + 1, "updated_at": now}
                ).model_dump()
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return link


def list_paper_links(conn, project_id: str) -> list[PaperLink]:
    _require_project(conn, project_id)
    rows = conn.execute(
        """SELECT p.payload_json FROM research_paper_link_versions p
        JOIN (SELECT link_id,MAX(version) version FROM research_paper_link_versions
              WHERE project_id=? GROUP BY link_id) x
          ON x.link_id=p.link_id AND x.version=p.version
        WHERE p.project_id=? ORDER BY p.created_at,p.link_id""",
        (project_id, project_id),
    ).fetchall()
    return [PaperLink.model_validate_json(r["payload_json"]) for r in rows]


def update_paper_link(
    conn, project_id: str, link_id: str, request: PaperLinkPatch
) -> PaperLink:
    _begin(conn)
    try:
        _require_project(conn, project_id)
        current = get_paper_link(conn, link_id)
        if current is None or current.project_id != project_id:
            raise NotFoundError("论文关联不存在")
        _check_version(current.version, request.expected_version, "论文关联")
        changes = request.model_dump(exclude={"expected_version"}, exclude_none=True)
        updated = PaperLink.model_validate(
            current.model_copy(
                update={**changes, "version": current.version + 1, "updated_at": _now()}
            ).model_dump()
        )
        conn.execute(
            "INSERT INTO research_paper_link_versions(link_id,project_id,version,paper_uid,status,payload_json,created_at) VALUES(?,?,?,?,?,?,?)",
            (
                updated.id,
                project_id,
                updated.version,
                updated.paper_uid,
                updated.status.value,
                _dump(updated),
                updated.updated_at.isoformat(),
            ),
        )
        if current.status != updated.status:
            _mark_snapshots(
                conn,
                [VersionRef(id=link_id, version=current.version)],
                [
                    "方案引用的论文关联已移除"
                    if updated.status.value == "removed"
                    else "论文关联状态已变化"
                ],
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return updated


FACT_MODELS = {
    "method": MethodCard,
    "experiment_setting": ExperimentSetting,
    "measurement": Measurement,
}


def _fact_kind(fact) -> str:
    if isinstance(fact, MethodCard):
        return "method"
    if isinstance(fact, ExperimentSetting):
        return "experiment_setting"
    if isinstance(fact, Measurement):
        return "measurement"
    raise TypeError("unsupported fact model")


def _insert_fact(conn, fact) -> None:
    conn.execute(
        "INSERT INTO research_fact_versions(fact_id,project_id,fact_kind,version,status,payload_json,created_at) VALUES(?,?,?,?,?,?,?)",
        (
            fact.id,
            fact.project_id,
            _fact_kind(fact),
            fact.version,
            fact.status.value,
            _dump(fact),
            (fact.updated_at or fact.created_at or _now()).isoformat(),
        ),
    )


def get_fact(conn, fact_id: str):
    row = _latest_row(conn, "research_fact_versions", "fact_id", fact_id)
    return (
        FACT_MODELS[row["fact_kind"]].model_validate_json(row["payload_json"])
        if row
        else None
    )


def list_facts(conn, project_id: str, *, kind=None, status=None, paper_link_id=None):
    _require_project(conn, project_id)
    if kind is not None and kind not in FACT_MODELS:
        raise ProjectStoreError("未知事实类型")
    rows = conn.execute(
        """SELECT f.* FROM research_fact_versions f
        JOIN (SELECT fact_id,MAX(version) version FROM research_fact_versions
              WHERE project_id=? GROUP BY fact_id) x
          ON x.fact_id=f.fact_id AND x.version=f.version
        WHERE f.project_id=? AND (? IS NULL OR f.fact_kind=?) AND (? IS NULL OR f.status=?)
        ORDER BY f.fact_kind,f.fact_id""",
        (project_id, project_id, kind, kind, status, status),
    ).fetchall()
    facts = [
        FACT_MODELS[r["fact_kind"]].model_validate_json(r["payload_json"]) for r in rows
    ]
    return [
        f
        for f in facts
        if paper_link_id is None or getattr(f, "paper_link_id", None) == paper_link_id
    ]


def list_evidence(conn, project_id: str) -> list[EvidenceRef]:
    _require_project(conn, project_id)
    rows = conn.execute(
        "SELECT payload_json FROM research_evidence WHERE project_id=? ORDER BY evidence_id",
        (project_id,),
    ).fetchall()
    return [EvidenceRef.model_validate_json(r["payload_json"]) for r in rows]


def save_candidate_bundle(conn, bundle: CandidateBundle) -> CandidateBundle:
    _begin(conn)
    try:
        _require_project(conn, bundle.project_id)
        link = get_paper_link(conn, bundle.paper_link_id)
        if (
            link is None
            or link.project_id != bundle.project_id
            or link.status.value != "active"
        ):
            raise NotFoundError("有效论文关联不存在")
        if (
            link.linked_document_id != bundle.document_id
            or link.linked_document_version != bundle.document_version
        ):
            raise InvalidStateError("候选来源文档与冻结论文关联不一致")
        for evidence in bundle.evidence:
            if evidence.source_kind.value == "literature_report" and (
                evidence.paper_uid != link.paper_uid
                or evidence.document_id != bundle.document_id
                or evidence.document_version != bundle.document_version
            ):
                raise InvalidStateError("文献证据与冻结论文或文档版本不一致")
            row = conn.execute(
                "SELECT project_id,payload_json FROM research_evidence WHERE evidence_id=?",
                (evidence.id,),
            ).fetchone()
            encoded = _dump(evidence)
            if row and (
                row["project_id"] != bundle.project_id or row["payload_json"] != encoded
            ):
                raise InvalidStateError("同一证据 ID 已属于其他内容或项目")
            if not row:
                conn.execute(
                    "INSERT INTO research_evidence(evidence_id,project_id,paper_link_id,payload_json,created_at) VALUES(?,?,?,?,?)",
                    (
                        evidence.id,
                        bundle.project_id,
                        bundle.paper_link_id,
                        encoded,
                        _now().isoformat(),
                    ),
                )
        known_evidence = {
            r["evidence_id"]
            for r in conn.execute(
                "SELECT evidence_id FROM research_evidence WHERE project_id=?",
                (bundle.project_id,),
            ).fetchall()
        }
        all_facts = [*bundle.methods, *bundle.experiment_settings, *bundle.measurements]
        if len({f.id for f in all_facts}) != len(all_facts):
            raise InvalidStateError("候选包内事实 ID 重复")
        changed: list[VersionRef] = []
        for fact in all_facts:
            if (
                fact.project_id != bundle.project_id
                or fact.status != RecordStatus.CANDIDATE
            ):
                raise InvalidStateError(
                    "新抽取事实必须属于当前项目并保持 candidate 状态"
                )
            if (
                getattr(fact, "paper_link_id", bundle.paper_link_id)
                != bundle.paper_link_id
            ):
                raise InvalidStateError("候选事实属于其他论文关联")
            refs = {eid for b in fact.field_evidence for eid in b.evidence_ids}
            if not refs.issubset(known_evidence):
                raise InvalidStateError("字段来源引用了当前项目之外的证据")
            current = get_fact(conn, fact.id)
            encoded = _dump(fact)
            if current:
                if current.project_id != bundle.project_id or _fact_kind(
                    current
                ) != _fact_kind(fact):
                    raise InvalidStateError("事实 ID 已属于其他项目或类型")
                if fact.version == current.version and encoded == _dump(current):
                    continue
                if fact.version != current.version + 1:
                    raise VersionConflictError(
                        "事实已更新，请重新加载", current_version=current.version
                    )
                changed.append(VersionRef(id=current.id, version=current.version))
            elif fact.version != 1:
                raise VersionConflictError("新事实必须从版本 1 开始", current_version=1)
            _insert_fact(conn, fact)
        method_ids = {f.id for f in list_facts(conn, bundle.project_id, kind="method")}
        if any(s.method_id not in method_ids for s in bundle.experiment_settings):
            raise InvalidStateError("实验设置引用了不存在的方法")
        setting_ids = {
            f.id for f in list_facts(conn, bundle.project_id, kind="experiment_setting")
        }
        if any(m.experiment_setting_id not in setting_ids for m in bundle.measurements):
            raise InvalidStateError("测量引用了不存在的实验设置")
        _mark_snapshots(conn, changed, ["引用事实已产生新版本"])
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return bundle


def transition_fact(
    conn, project_id: str, fact_id: str, request: StatusTransitionRequest
):
    _begin(conn)
    try:
        _require_project(conn, project_id)
        current = get_fact(conn, fact_id)
        if current is None or current.project_id != project_id:
            raise NotFoundError("事实不存在")
        _check_version(current.version, request.expected_version, "事实")
        if current.status != request.from_status:
            raise VersionConflictError(
                "事实状态已更新，请重新加载", current_version=current.version
            )
        if request.to_status not in ALLOWED_RECORD_STATUS_TRANSITIONS[current.status]:
            raise InvalidStateError("不允许的事实状态转换")
        now = _now()
        updated = type(current).model_validate(
            current.model_copy(
                update={
                    "version": current.version + 1,
                    "status": request.to_status,
                    "updated_at": now,
                }
            ).model_dump()
        )
        _insert_fact(conn, updated)
        conn.execute(
            """INSERT INTO research_fact_audit(project_id,fact_id,from_version,to_version,action,actor,reason,before_json,after_json,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                project_id,
                fact_id,
                current.version,
                updated.version,
                f"{current.status.value}->{updated.status.value}",
                request.actor,
                request.reason,
                _dump(current),
                _dump(updated),
                now.isoformat(),
            ),
        )
        _mark_snapshots(
            conn,
            [VersionRef(id=fact_id, version=current.version)],
            [f"引用事实 {fact_id} 已产生新版本并变为 {updated.status.value}"],
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return updated


def _require_live_fact(conn, project_id: str, fact_id: str):
    fact = get_fact(conn, fact_id)
    if fact is None or fact.project_id != project_id:
        raise NotFoundError(f"事实 {fact_id} 不存在")
    if fact.status == RecordStatus.WITHDRAWN:
        raise InvalidStateError(f"事实 {fact_id} 已撤回")
    return fact


def fact_audit(conn, fact_id: str) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM research_fact_audit WHERE fact_id=? ORDER BY id", (fact_id,)
        ).fetchall()
    ]


def get_decision(conn, decision_id: str) -> ResearchDecision | None:
    row = _latest_row(conn, "research_decision_versions", "decision_id", decision_id)
    return ResearchDecision.model_validate_json(row["payload_json"]) if row else None


def list_decisions(conn, project_id: str) -> list[ResearchDecision]:
    _require_project(conn, project_id)
    rows = conn.execute(
        """SELECT d.payload_json FROM research_decision_versions d
        JOIN (SELECT decision_id,MAX(version) version FROM research_decision_versions WHERE project_id=? GROUP BY decision_id) x
          ON x.decision_id=d.decision_id AND x.version=d.version
        WHERE d.project_id=? ORDER BY d.created_at,d.decision_id""",
        (project_id, project_id),
    ).fetchall()
    return [ResearchDecision.model_validate_json(r["payload_json"]) for r in rows]


def save_decision(
    conn, project_id: str, request: ResearchDecisionCreate
) -> ResearchDecision:
    _begin(conn)
    try:
        project = _require_project(conn, project_id)
        _check_version(project.version, request.expected_project_version, "项目")
        method = _require_live_fact(conn, project_id, request.selected_method_id)
        if not isinstance(method, MethodCard):
            raise InvalidStateError("selected_method_id 必须引用方法事实")
        for setting_id in request.selected_experiment_setting_ids:
            setting = _require_live_fact(conn, project_id, setting_id)
            if (
                not isinstance(setting, ExperimentSetting)
                or setting.method_id != method.id
            ):
                raise InvalidStateError("选中实验设置与选中方法不一致")
        for fact_id in request.considered_candidate_ids:
            _require_live_fact(conn, project_id, fact_id)
        known = {e.id for e in list_evidence(conn, project_id)}
        if not set(request.evidence_ids).issubset(known):
            raise NotFoundError("决策引用了不存在的证据")
        now = _now()
        for prior in list_decisions(conn, project_id):
            if prior.status == DecisionStatus.ACTIVE:
                superseded = ResearchDecision.model_validate(
                    prior.model_copy(
                        update={
                            "version": prior.version + 1,
                            "status": DecisionStatus.SUPERSEDED,
                        }
                    ).model_dump()
                )
                conn.execute(
                    "INSERT INTO research_decision_versions VALUES(?,?,?,?,?,?)",
                    (
                        superseded.id,
                        project_id,
                        superseded.version,
                        superseded.status.value,
                        _dump(superseded),
                        now.isoformat(),
                    ),
                )
                _mark_snapshots(
                    conn,
                    [VersionRef(id=prior.id, version=prior.version)],
                    ["路线决策已被新决策取代"],
                )
        decision = ResearchDecision(
            id=_new_id("decision"),
            project_id=project_id,
            version=1,
            project_version=project.version,
            selected_method_id=request.selected_method_id,
            selected_experiment_setting_ids=request.selected_experiment_setting_ids,
            considered_candidate_ids=request.considered_candidate_ids,
            rationale=request.rationale,
            evidence_ids=request.evidence_ids,
            created_at=now,
        )
        conn.execute(
            "INSERT INTO research_decision_versions VALUES(?,?,?,?,?,?)",
            (
                decision.id,
                project_id,
                1,
                decision.status.value,
                _dump(decision),
                now.isoformat(),
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return decision


def get_plan(conn, plan_id: str) -> ValidationPlan | None:
    row = _latest_row(conn, "research_plan_versions", "plan_id", plan_id)
    return ValidationPlan.model_validate_json(row["payload_json"]) if row else None


def get_plan_version(conn, plan_id: str, version: int) -> ValidationPlan | None:
    row = conn.execute(
        "SELECT payload_json FROM research_plan_versions WHERE plan_id=? AND version=?",
        (plan_id, version),
    ).fetchone()
    return ValidationPlan.model_validate_json(row["payload_json"]) if row else None


def list_plans(conn, project_id: str) -> list[ValidationPlan]:
    _require_project(conn, project_id)
    rows = conn.execute(
        """SELECT p.payload_json FROM research_plan_versions p
        JOIN (SELECT plan_id,MAX(version) version FROM research_plan_versions WHERE project_id=? GROUP BY plan_id) x
          ON x.plan_id=p.plan_id AND x.version=p.version
        WHERE p.project_id=? ORDER BY p.created_at,p.plan_id""",
        (project_id, project_id),
    ).fetchall()
    return [ValidationPlan.model_validate_json(r["payload_json"]) for r in rows]


def save_plan(conn, project_id: str, request: PlanSaveRequest) -> ValidationPlan:
    _begin(conn)
    try:
        project = _require_project(conn, project_id)
        _check_version(project.version, request.expected_project_version, "项目")
        if request.plan.project_id != project_id:
            raise InvalidStateError("方案属于其他项目")
        method = _require_live_fact(conn, project_id, request.plan.selected_method_id)
        if not isinstance(method, MethodCard):
            raise InvalidStateError("方案方法引用无效")
        for sid in request.plan.selected_experiment_setting_ids:
            setting = _require_live_fact(conn, project_id, sid)
            if (
                not isinstance(setting, ExperimentSetting)
                or setting.method_id != method.id
            ):
                raise InvalidStateError("方案实验设置与方法不一致")
        plan_id = request.plan.id or _new_id("plan")
        current = get_plan(conn, plan_id)
        if current is not None and current.project_id != project_id:
            raise InvalidStateError("方案 ID 已属于其他项目")
        actual = current.version if current else 0
        _check_version(actual, request.expected_plan_version, "方案")
        saved = ValidationPlan.model_validate(
            request.plan.model_copy(
                update={
                    "id": plan_id,
                    "version": actual + 1,
                    "status": PlanStatus.SAVED,
                }
            ).model_dump()
        )
        conn.execute(
            "INSERT INTO research_plan_versions VALUES(?,?,?,?,?,?)",
            (
                plan_id,
                project_id,
                saved.version,
                saved.status.value,
                _dump(saved),
                _now().isoformat(),
            ),
        )
        if current:
            _mark_snapshots(
                conn,
                [VersionRef(id=plan_id, version=current.version)],
                ["验证方案已产生新版本"],
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return saved


def _snapshot_from_row(row) -> ProjectSnapshot:
    value = ProjectSnapshot.model_validate_json(row["payload_json"])
    return ProjectSnapshot.model_validate(
        value.model_copy(
            update={
                "review_status": ReviewStatus(row["review_status"]),
                "review_reasons": json.loads(row["review_reasons_json"]),
            }
        ).model_dump()
    )


def get_snapshot(conn, project_id: str, snapshot_id: str) -> ProjectSnapshot | None:
    row = conn.execute(
        "SELECT * FROM research_snapshots WHERE project_id=? AND snapshot_id=?",
        (project_id, snapshot_id),
    ).fetchone()
    return _snapshot_from_row(row) if row else None


def list_snapshots(conn, project_id: str) -> list[ProjectSnapshot]:
    _require_project(conn, project_id)
    return [
        _snapshot_from_row(r)
        for r in conn.execute(
            "SELECT * FROM research_snapshots WHERE project_id=? ORDER BY snapshot_version",
            (project_id,),
        ).fetchall()
    ]


def save_snapshot(conn, snapshot: ProjectSnapshot) -> ProjectSnapshot:
    _begin(conn)
    try:
        _require_project(conn, snapshot.project_id)
        row = conn.execute(
            "SELECT * FROM research_snapshots WHERE snapshot_id=?", (snapshot.id,)
        ).fetchone()
        if row:
            current = _snapshot_from_row(row)
            if current == snapshot:
                conn.rollback()
                return current
            raise InvalidStateError("快照不可修改")
        expected = conn.execute(
            "SELECT COALESCE(MAX(snapshot_version),0)+1 n FROM research_snapshots WHERE project_id=?",
            (snapshot.project_id,),
        ).fetchone()["n"]
        if snapshot.snapshot_version != expected:
            raise VersionConflictError(
                "快照版本已更新，请重新加载", current_version=max(1, expected - 1)
            )
        prow = conn.execute(
            "SELECT payload_json FROM research_project_versions WHERE project_id=? AND version=?",
            (snapshot.project_id, snapshot.frozen_project_version),
        ).fetchone()
        if not prow:
            raise NotFoundError("快照引用的项目版本不存在")
        frozen_project = ResearchProject.model_validate_json(prow["payload_json"])
        if (
            snapshot.frozen_constraint_version != frozen_project.constraints.version
            or snapshot.frozen_domain_profile_version
            != frozen_project.domain_profile_version
        ):
            raise InvalidStateError("快照项目、约束或领域配置版本不一致")
        drow = conn.execute(
            "SELECT payload_json FROM research_decision_versions WHERE decision_id=? AND version=?",
            (snapshot.frozen_decision.id, snapshot.frozen_decision.version),
        ).fetchone()
        if (
            not drow
            or ResearchDecision.model_validate_json(drow["payload_json"]).project_id
            != snapshot.project_id
        ):
            raise NotFoundError("快照引用的决策版本不存在")
        if snapshot.plan.id is None:
            raise InvalidStateError("快照中的方案必须是已保存版本")
        saved_plan = get_plan_version(conn, snapshot.plan.id, snapshot.plan.version)
        if (
            saved_plan is None
            or saved_plan.project_id != snapshot.project_id
            or saved_plan != snapshot.plan
        ):
            raise InvalidStateError("快照方案与已保存版本不一致")
        for ref in snapshot.frozen_facts:
            frow = conn.execute(
                "SELECT project_id FROM research_fact_versions WHERE fact_id=? AND version=?",
                (ref.id, ref.version),
            ).fetchone()
            if not frow or frow["project_id"] != snapshot.project_id:
                raise NotFoundError(f"快照引用的事实版本不存在: {ref.id}")
        for doc in snapshot.frozen_documents:
            link = get_paper_link(conn, doc.paper_link_id)
            hash_row = conn.execute(
                "SELECT content_hash FROM documents WHERE id=? AND paper_uid=?",
                (doc.document_id, doc.paper_uid),
            ).fetchone()
            if (
                not link
                or link.project_id != snapshot.project_id
                or link.paper_uid != doc.paper_uid
                or link.linked_document_id != doc.document_id
                or link.linked_document_version != doc.document_version
                or not hash_row
                or hash_row["content_hash"] != doc.content_hash
            ):
                raise InvalidStateError("快照文档与冻结论文关联不一致")
        now = snapshot.created_at.isoformat()
        conn.execute(
            "INSERT INTO research_snapshots VALUES(?,?,?,?,?,?,?)",
            (
                snapshot.id,
                snapshot.project_id,
                snapshot.snapshot_version,
                _dump(snapshot),
                snapshot.review_status.value,
                json.dumps(snapshot.review_reasons, ensure_ascii=False),
                now,
            ),
        )
        deps = [
            ("project", snapshot.project_id, snapshot.frozen_project_version),
            ("decision", snapshot.frozen_decision.id, snapshot.frozen_decision.version),
            ("plan", snapshot.plan.id, snapshot.plan.version),
        ]
        deps += [("fact", r.id, r.version) for r in snapshot.frozen_facts]
        deps += [("paper_link", d.paper_link_id, -1) for d in snapshot.frozen_documents]
        conn.executemany(
            "INSERT INTO research_snapshot_dependencies VALUES(?,?,?,?)",
            [(snapshot.id, kind, ref, version) for kind, ref, version in deps],
        )
        conn.execute(
            "INSERT INTO research_projection_outbox(snapshot_id,project_id,status,attempt_count,last_error,created_at,updated_at) VALUES(?,?,'pending',0,NULL,?,?)",
            (snapshot.id, snapshot.project_id, now, now),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return snapshot


def _mark_snapshots(
    conn, changed_refs: Iterable[VersionRef], reasons: list[str]
) -> int:
    ids = {r.id for r in changed_refs}
    if not ids or not reasons:
        return 0
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"""SELECT DISTINCT s.snapshot_id,s.review_reasons_json FROM research_snapshots s
        JOIN research_snapshot_dependencies d ON d.snapshot_id=s.snapshot_id
        WHERE d.ref_id IN ({placeholders})""",
        tuple(ids),
    ).fetchall()
    for row in rows:
        existing = json.loads(row["review_reasons_json"])
        merged = existing + [r for r in reasons if r not in existing]
        conn.execute(
            "UPDATE research_snapshots SET review_status=?,review_reasons_json=? WHERE snapshot_id=?",
            (
                ReviewStatus.NEEDS_REVIEW.value,
                json.dumps(merged, ensure_ascii=False),
                row["snapshot_id"],
            ),
        )
    return len(rows)


def mark_dependent_snapshots_for_review(
    conn, changed_refs: list[VersionRef], reasons: list[str]
) -> int:
    _begin(conn)
    try:
        count = _mark_snapshots(conn, changed_refs, reasons)
        conn.commit()
        return count
    except Exception:
        conn.rollback()
        raise


def get_projection_state(conn, snapshot_id: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM research_projection_outbox WHERE snapshot_id=?", (snapshot_id,)
    ).fetchone()
    return dict(row) if row else None


def update_projection_state(
    conn, snapshot_id: str, status: str, *, error: str | None = None
) -> dict:
    if status not in {"pending", "running", "succeeded", "failed"}:
        raise ValueError("invalid projection status")
    _begin(conn)
    try:
        row = conn.execute(
            "SELECT * FROM research_projection_outbox WHERE snapshot_id=?",
            (snapshot_id,),
        ).fetchone()
        if not row:
            raise NotFoundError("投影待同步记录不存在")
        attempts = row["attempt_count"] + (1 if status == "running" else 0)
        conn.execute(
            "UPDATE research_projection_outbox SET status=?,attempt_count=?,last_error=?,updated_at=? WHERE snapshot_id=?",
            (status, attempts, error, _now().isoformat(), snapshot_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return get_projection_state(conn, snapshot_id)


def _task_from_row(row) -> AsyncTask:
    return AsyncTask(
        id=row["task_id"],
        kind=row["kind"],
        status=row["status"],
        project_id=row["project_id"],
        progress=row["progress"],
        result=json.loads(row["result_json"]) if row["result_json"] else None,
        error=ErrorDetail.model_validate_json(row["error_json"])
        if row["error_json"]
        else None,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def get_task(conn, task_id: str) -> AsyncTask | None:
    row = conn.execute(
        "SELECT * FROM research_async_tasks WHERE task_id=?", (task_id,)
    ).fetchone()
    return _task_from_row(row) if row else None


def get_task_params(conn, task_id: str) -> dict:
    row = conn.execute(
        "SELECT params_json FROM research_async_tasks WHERE task_id=?", (task_id,)
    ).fetchone()
    if not row:
        raise NotFoundError("任务不存在")
    return json.loads(row["params_json"])


def get_or_create_task(
    conn, kind: TaskKind, project_id: str, params: dict, *, retry_of=None
) -> tuple[AsyncTask, bool]:
    encoded = json.dumps(
        params, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    _begin(conn)
    try:
        _require_project(conn, project_id)
        row = conn.execute(
            "SELECT * FROM research_async_tasks WHERE kind=? AND project_id=? AND params_json=? AND status IN ('queued','running') ORDER BY created_at LIMIT 1",
            (kind.value, project_id, encoded),
        ).fetchone()
        if row:
            conn.rollback()
            return _task_from_row(row), False
        now = _now()
        task = AsyncTask(
            id=_new_id("task"),
            kind=kind,
            status=TaskStatus.QUEUED,
            project_id=project_id,
            created_at=now,
            updated_at=now,
        )
        conn.execute(
            """INSERT INTO research_async_tasks
          (task_id,kind,status,project_id,progress,params_json,result_json,error_json,retry_of,created_at,updated_at)
          VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (
                task.id,
                kind.value,
                task.status.value,
                project_id,
                None,
                encoded,
                None,
                None,
                retry_of,
                now.isoformat(),
                now.isoformat(),
            ),
        )
        conn.commit()
        return task, True
    except Exception:
        conn.rollback()
        raise


def create_task(
    conn, kind: TaskKind, project_id: str, params: dict, *, retry_of=None
) -> AsyncTask:
    return get_or_create_task(conn, kind, project_id, params, retry_of=retry_of)[0]


def update_task(
    conn, task_id: str, status: TaskStatus, *, progress=None, result=None, error=None
) -> AsyncTask:
    current = get_task(conn, task_id)
    if current is None:
        raise NotFoundError("任务不存在")
    if current.status in {
        TaskStatus.SUCCEEDED,
        TaskStatus.FAILED,
        TaskStatus.INTERRUPTED,
    }:
        if current.status == status:
            return current
        raise InvalidStateError("终态任务不可再次变更")
    allowed = {
        TaskStatus.QUEUED: {
            TaskStatus.RUNNING,
            TaskStatus.FAILED,
            TaskStatus.INTERRUPTED,
        },
        TaskStatus.RUNNING: {
            TaskStatus.SUCCEEDED,
            TaskStatus.FAILED,
            TaskStatus.INTERRUPTED,
        },
    }
    if status not in allowed[current.status]:
        raise InvalidStateError("不允许的任务状态转换")
    if status == TaskStatus.SUCCEEDED and result is None:
        raise InvalidStateError("成功任务必须包含结果")
    if status == TaskStatus.FAILED and error is None:
        raise InvalidStateError("失败任务必须包含错误")
    if status != TaskStatus.FAILED and error is not None:
        raise InvalidStateError("只有失败任务可以包含错误")
    _begin(conn)
    try:
        conn.execute(
            "UPDATE research_async_tasks SET status=?,progress=?,result_json=?,error_json=?,updated_at=? WHERE task_id=?",
            (
                status.value,
                progress,
                json.dumps(result, ensure_ascii=False) if result is not None else None,
                error.model_dump_json() if error else None,
                _now().isoformat(),
                task_id,
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return get_task(conn, task_id)


def interrupt_incomplete_tasks(conn) -> int:
    now = _now().isoformat()
    cur = conn.execute(
        "UPDATE research_async_tasks SET status='interrupted',updated_at=? WHERE status IN ('queued','running')",
        (now,),
    )
    conn.commit()
    return cur.rowcount
