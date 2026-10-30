"""Explain downstream effects of deterministic source checks without mutating records."""

from urllib.parse import quote

from app.research.audit import project_audit
from app.workflow import activities


def project_impact(conn, project_id: str) -> dict:
    audit = project_audit(conn, project_id)
    project_tasks = activities(conn, "project", project_id=project_id)
    roadmap_tasks = activities(conn, "roadmap")
    issues = []
    for issue in audit["issues"]:
        affected = []
        for plan_id in issue["affected_plan_ids"]:
            affected.append({"kind": "plan", "id": plan_id,
                             "url": f"/research/{quote(project_id, safe='')}?tab=plans",
                             "reason": "方案使用了此问题涉及的来源或事实"})
        for snapshot_id in issue["affected_snapshot_ids"]:
            affected.append({"kind": "snapshot", "id": snapshot_id,
                             "url": f"/research/{quote(project_id, safe='')}?tab=changes&snapshot={quote(snapshot_id, safe='')}",
                             "reason": "不可变快照保留原值，当前依据需要复核"})
        for task in project_tasks:
            if task["source_id"] in issue["affected_snapshot_ids"]:
                affected.append({"kind": "activity", "id": task["id"], "url": task["url"],
                                 "reason": "快照步骤依赖存在问题的依据"})
        for task in roadmap_tasks:
            if task.get("item_uid") in issue["paper_uids"] or set(task["evidence_ids"]) & set(issue["evidence_ids"]):
                affected.append({"kind": "activity", "id": task["id"], "url": task["url"],
                                 "reason": "路线任务使用了此问题涉及的论文或依据"})
        issues.append({"issue_id": issue["id"], "code": issue["code"],
                       "severity": issue["severity"], "source_refs": [
                           *({"kind": "paper", "id": value} for value in issue["paper_uids"]),
                           *({"kind": "fact", "id": value} for value in issue["fact_ids"]),
                           *({"kind": "evidence", "id": value} for value in issue["evidence_ids"]),
                       ], "affected": sorted(affected, key=lambda item: (item["kind"], item["id"]))})
    return {"contract_version": "project-impact-v1", "project_id": project_id,
            "input_fingerprint": audit["input_fingerprint"], "issues": issues,
            "notice": "影响范围由当前来源链自动计算；不修改既有事实、方案、快照或正式路线。"}
