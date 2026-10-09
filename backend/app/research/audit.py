"""Read-only, deterministic project evidence audit.

Checks establish source integrity and comparability, never scientific truth.
"""

from __future__ import annotations

import hashlib
import json
from itertools import combinations

from app.db import projects as store
from app.research.service import project_facts

RULE_VERSION = "project-audit-1"


def _normal(value: str | None) -> str:
    return " ".join((value or "").casefold().split())


def project_audit(conn, project_id: str) -> dict:
    project = store.get_project(conn, project_id)
    if project is None:
        raise store.NotFoundError("项目不存在")
    facts = project_facts(conn, project_id)
    links = store.list_paper_links(conn, project_id)
    plans = store.list_plans(conn, project_id)
    snapshots = store.list_snapshots(conn, project_id)
    active = {link.id: link for link in links if link.status.value == "active"}
    documents = {
        row["id"]: dict(row)
        for row in conn.execute(
            "SELECT rowid,id,paper_uid,content_hash,coverage,created_at FROM documents "
            "WHERE paper_uid IN (SELECT DISTINCT paper_uid FROM research_paper_link_versions "
            "WHERE project_id=?)",
            (project_id,),
        )
    }
    passages = {
        row["id"]: dict(row)
        for row in conn.execute(
            "SELECT p.id,p.document_id,p.text,p.page FROM passages p JOIN documents d "
            "ON d.id=p.document_id WHERE d.paper_uid IN "
            "(SELECT DISTINCT paper_uid FROM research_paper_link_versions WHERE project_id=?)",
            (project_id,),
        )
    }
    evidence = {item.id: item for item in facts.evidence}
    all_facts = [*facts.methods, *facts.experiment_settings, *facts.measurements]
    methods = {item.id: item for item in facts.methods}
    settings = {item.id: item for item in facts.experiment_settings}
    issues: list[dict] = []

    def add(code, severity, title, detail, *, fact_ids=(), evidence_ids=(), paper_uids=(), plan_ids=()):
        fact_ids = sorted(set(fact_ids))
        evidence_ids = sorted(set(evidence_ids))
        paper_uids = sorted(set(paper_uids))
        plan_ids = sorted(set(plan_ids))
        key = json.dumps([code, fact_ids, evidence_ids, paper_uids, plan_ids], ensure_ascii=False)
        issue_id = hashlib.sha256(key.encode()).hexdigest()[:16]
        issues.append(
            dict(id=issue_id, code=code, severity=severity, title=title,
                 detail=detail, fact_ids=fact_ids, evidence_ids=evidence_ids,
                 paper_uids=paper_uids, affected_plan_ids=plan_ids, affected_snapshot_ids=[])
        )

    for link in active.values():
        doc = documents.get(link.linked_document_id or "")
        if not doc or link.linked_document_version != f"sha256:{doc['content_hash']}":
            add("source_version_unavailable", "blocking", "冻结来源版本不可用",
                f"论文关联 {link.id} 无法对应到已保存的文档版本。", paper_uids=[link.paper_uid])
            continue
        if doc["coverage"] != "fulltext":
            add("abstract_only", "warning", "仅有摘要资料",
                f"论文 {link.paper_uid} 缺少全文，实验条件可能未被解析。", paper_uids=[link.paper_uid])
        newer = any(
            other["paper_uid"] == link.paper_uid and other["id"] != doc["id"]
            and (other["created_at"], other["rowid"]) > (doc["created_at"], doc["rowid"])
            for other in documents.values()
        )
        if newer:
            add("newer_document", "notice", "存在更新的文档版本",
                f"论文 {link.paper_uid} 的课题关联仍固定在原版本；请检查更新的影响。",
                paper_uids=[link.paper_uid])

    for fact in all_facts:
        if fact.status.value == "withdrawn":
            continue
        link_id = getattr(fact, "paper_link_id", None)
        if link_id and link_id not in active:
            add("inactive_source", "blocking", "事实来源已移除",
                f"事实 {fact.id} 关联的论文不再有效。", fact_ids=[fact.id])
        for field in fact.field_evidence:
            if field.source_kind.value != "literature_report":
                continue
            if field.finding_status.value == "reported" and not field.evidence_ids:
                add("unbound_field", "blocking", "报告字段没有来源",
                    f"{fact.id}.{field.field_path} 缺少证据绑定。", fact_ids=[fact.id])
            for evidence_id in field.evidence_ids:
                item = evidence.get(evidence_id)
                if item is None:
                    add("missing_evidence", "blocking", "证据记录不可用",
                        f"{fact.id}.{field.field_path} 指向不存在的证据 {evidence_id}。",
                        fact_ids=[fact.id], evidence_ids=[evidence_id])
                    continue
                if item.source_kind.value != "literature_report":
                    continue
                matching_links = [link for link in active.values()
                                  if link.paper_uid == item.paper_uid
                                  and link.linked_document_id == item.document_id
                                  and link.linked_document_version == item.document_version]
                doc = documents.get(item.document_id or "")
                if not matching_links or not doc or item.document_version != f"sha256:{doc['content_hash']}":
                    add("evidence_version_mismatch", "blocking", "证据与冻结来源不匹配",
                        f"证据 {evidence_id} 未指向本课题当前关联的文档版本。",
                        fact_ids=[fact.id], evidence_ids=[evidence_id],
                        paper_uids=[item.paper_uid] if item.paper_uid else [])
                    continue
                if item.passage_id:
                    passage = passages.get(item.passage_id)
                    if not passage or passage["document_id"] != item.document_id:
                        add("passage_missing", "blocking", "原文片段不可定位",
                            f"证据 {evidence_id} 的片段不存在或属于另一文档。",
                            fact_ids=[fact.id], evidence_ids=[evidence_id], paper_uids=[item.paper_uid])
                    elif item.quote and item.quote not in passage["text"]:
                        add("quote_mismatch", "blocking", "引文与片段文字不一致",
                            f"证据 {evidence_id} 的引文无法在绑定片段中精确定位。",
                            fact_ids=[fact.id], evidence_ids=[evidence_id], paper_uids=[item.paper_uid])
        if fact.finding_status.value == "conflicting":
            add("recorded_conflict", "warning", "来源记录为冲突",
                f"事实 {fact.id} 的冲突状态仍未消除。", fact_ids=[fact.id])

    for setting in settings.values():
        if setting.status.value == "withdrawn":
            continue
        missing = [name for name in ("dataset", "split", "evaluation_protocol")
                   if not getattr(setting, name)]
        if missing:
            add("missing_conditions", "warning", "实验条件不完整",
                f"设置 {setting.name} 缺少：{', '.join(missing)}；不能据此认定同条件可比。",
                fact_ids=[setting.id])

    measurements = sorted((item for item in facts.measurements
                           if item.status.value != "withdrawn" and item.value is not None
                           and item.experiment_setting_id in settings), key=lambda item: item.id)
    # Pairwise checks are bounded; no comparison score or winner is inferred.
    eligible = measurements[:100]
    for left, right in combinations(eligible, 2):
        a, b = settings[left.experiment_setting_id], settings[right.experiment_setting_id]
        if a.id == b.id or not a.dataset or _normal(a.dataset) != _normal(b.dataset):
            continue
        if _normal(left.metric_name) != _normal(right.metric_name):
            continue
        if (_normal(left.metric_scope) != _normal(right.metric_scope)
                or left.direction != right.direction
                or left.value.scale != right.value.scale
                or left.value.unit != right.value.unit):
            add("incompatible_metric_scope", "warning", "指标范围或单位不可直接比较",
                f"{a.name} 与 {b.name} 的指标范围、方向、量纲或单位不同。",
                fact_ids=[a.id, b.id, left.id, right.id])
            continue
        if not all((a.split, b.split, a.evaluation_protocol, b.evaluation_protocol)):
            continue
        if _normal(a.split) != _normal(b.split) or _normal(a.evaluation_protocol) != _normal(b.evaluation_protocol):
            add("incompatible_conditions", "warning", "同名指标的条件不可直接比较",
                f"{a.name} 与 {b.name} 使用不同的数据划分或评估协议。",
                fact_ids=[a.id, b.id, left.id, right.id])
        elif (_normal(methods.get(a.method_id).name if methods.get(a.method_id) else "")
              == _normal(methods.get(b.method_id).name if methods.get(b.method_id) else "")
              and left.value.scale == right.value.scale and left.value.unit == right.value.unit
              and left.value.value != right.value.value):
            add("reported_value_divergence", "notice", "同条件报告值不同",
                f"{a.name} 与 {b.name} 的同名测量值不同；可能来自不同运行，需查看原文。",
                fact_ids=[a.id, b.id, left.id, right.id])
    if len(measurements) > len(eligible):
        add("pair_check_truncated", "notice", "跨论文检查范围受限",
            f"本次仅检查前 {len(eligible)} 条有数值的测量，剩余测量未参与成对检查。")

    for plan in plans:
        plan_ids = [plan.id] if plan.id else []
        if not plan.steps or not plan.target_measurements:
            add("plan_measurement_gap", "warning", "方案缺少可执行步骤或目标测量",
                f"方案 {plan.title} 尚未同时给出步骤与目标测量。", plan_ids=plan_ids)
        for step in plan.steps:
            missing = [name for name in ("inputs", "procedure", "acceptance_criteria")
                       if not getattr(step, name)]
            if missing:
                add("plan_step_gap", "warning", "方案步骤信息不足",
                    f"步骤 {step.title} 缺少：{', '.join(missing)}。", plan_ids=plan_ids)
            absent = [eid for eid in step.evidence_ids if eid not in evidence]
            if absent:
                add("plan_step_evidence_missing", "blocking", "方案步骤来源不可用",
                    f"步骤 {step.title} 指向不存在的证据。", evidence_ids=absent,
                    plan_ids=plan_ids)
        for setting_id in plan.selected_experiment_setting_ids:
            setting = settings.get(setting_id)
            if setting and (not setting.random_seed or not setting.resources):
                add("plan_reproducibility_gap", "notice", "复现参数仍有缺口",
                    f"方案 {plan.title} 使用的设置 {setting.name} 缺少随机种子或计算资源记录。",
                    fact_ids=[setting.id], plan_ids=plan_ids)
        if plan.review_status.value == "needs_review":
            add("plan_needs_review", "warning", "方案已有待复核标记",
                "; ".join(plan.review_reasons) or plan.title,
                fact_ids=[plan.selected_method_id, *plan.selected_experiment_setting_ids])
    for snapshot in snapshots:
        if snapshot.review_status.value == "needs_review":
            add("snapshot_needs_review", "warning", "快照已有待复核标记",
                "; ".join(snapshot.review_reasons) or snapshot.id,
                fact_ids=[ref.id for ref in snapshot.frozen_facts])

    paper_by_link = {link.id: link.paper_uid for link in links}
    measurement_setting = {item.id: item.experiment_setting_id for item in facts.measurements}

    def plan_facts(plan):
        return {plan.selected_method_id, *plan.selected_experiment_setting_ids,
                *(measurement_id for measurement_id, setting_id in measurement_setting.items()
                  if setting_id in plan.selected_experiment_setting_ids)}

    def plan_papers(plan):
        selected = [methods.get(plan.selected_method_id),
                    *(settings.get(identity) for identity in plan.selected_experiment_setting_ids)]
        return {paper_by_link.get(item.paper_link_id) for item in selected if item and item.paper_link_id}

    for issue in issues:
        touched_facts = set(issue["fact_ids"])
        touched_evidence = set(issue["evidence_ids"])
        touched_papers = set(issue["paper_uids"])
        issue["affected_plan_ids"] = sorted(set(issue["affected_plan_ids"]) | {
            plan.id for plan in plans if plan.id and (
                bool(plan_facts(plan) & touched_facts)
                or bool(plan_papers(plan) & touched_papers)
                or any(set(step.evidence_ids) & touched_evidence for step in plan.steps)
            )
        })
        issue["affected_snapshot_ids"] = sorted(
            snapshot.id for snapshot in snapshots if (
                bool({ref.id for ref in snapshot.frozen_facts} & touched_facts)
                or bool({doc.paper_uid for doc in snapshot.frozen_documents} & touched_papers)
                or any(set(step.evidence_ids) & touched_evidence for step in snapshot.plan.steps)
            )
        )
    issues.sort(key=lambda item: ({"blocking": 0, "warning": 1, "notice": 2}[item["severity"]], item["code"], item["id"]))
    payload = dict(project=project.model_dump(mode="json"),
                   links=[x.model_dump(mode="json") for x in links],
                   facts=facts.model_dump(mode="json"),
                   plans=[x.model_dump(mode="json") for x in plans],
                   snapshots=[x.model_dump(mode="json") for x in snapshots],
                   documents=documents, passages=passages, rule=RULE_VERSION)
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return dict(contract_version="project-audit-v1", rule_version=RULE_VERSION,
                project_id=project_id, input_fingerprint=digest,
                summary={level: sum(i["severity"] == level for i in issues)
                         for level in ("blocking", "warning", "notice")}, issues=issues,
                notice="自动核查只确认来源可定位与条件可比性，不证明科研结论正确。")
