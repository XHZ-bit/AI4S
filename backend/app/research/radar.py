"""Local-corpus literature radar; deterministic hints, not scientific judgments."""

from __future__ import annotations

import hashlib
import json
from urllib.parse import quote

from app.db import projects as store
from app.research.service import project_facts

RULE_VERSION = "local-radar-1"


def radar(conn, project_id: str) -> dict:
    project = store.get_project(conn, project_id)
    if project is None:
        raise store.NotFoundError("项目不存在")
    links = store.list_paper_links(conn, project_id)
    linked = {item.paper_uid for item in links if item.status.value == "active"}
    facts = project_facts(conn, project_id)
    plans = store.list_plans(conn, project_id)
    methods = {item.id: item for item in facts.methods if item.status.value != "withdrawn"}
    settings = {item.id: item for item in facts.experiment_settings if item.status.value != "withdrawn"}
    terms: dict[str, set[str]] = {}
    for method in methods.values():
        if len(method.name.strip()) >= 4:
            terms.setdefault(method.name.casefold().strip(), set()).add(f"方法：{method.name}")
    for setting in settings.values():
        if setting.dataset and len(setting.dataset.strip()) >= 4:
            terms.setdefault(setting.dataset.casefold().strip(), set()).add(f"数据集：{setting.dataset}")
    for dataset in project.constraints.allowed_datasets:
        if len(dataset.strip()) >= 4:
            terms.setdefault(dataset.casefold().strip(), set()).add(f"课题数据集：{dataset}")
    papers = [dict(row) for row in conn.execute(
        "SELECT uid,title,abstract,year,source,created_at FROM papers ORDER BY created_at DESC,uid"
    ) if row["uid"] not in linked]
    matches = []
    for paper in papers:
        haystack = f"{paper['title']}\n{paper['abstract']}".casefold()
        hit = sorted({reason for term, reasons in terms.items() if term in haystack for reason in reasons})
        if not hit:
            continue
        plan_ids = []
        for plan in plans:
            selected_method = methods.get(plan.selected_method_id)
            selected_settings = [settings.get(identity) for identity in plan.selected_experiment_setting_ids]
            relevant = (
                selected_method is not None and f"方法：{selected_method.name}" in hit
            ) or any(
                item and item.dataset and (
                    f"数据集：{item.dataset}" in hit or f"课题数据集：{item.dataset}" in hit
                ) for item in selected_settings
            )
            if relevant and plan.id:
                plan_ids.append(plan.id)
        matches.append(dict(uid=paper["uid"], title=paper["title"], year=paper["year"],
                            source=paper["source"], created_at=paper["created_at"],
                            match_reasons=hit, potentially_affected_plan_ids=sorted(set(plan_ids)),
                            source_url=f"/papers/{quote(paper['uid'], safe='')}"))
    matches.sort(key=lambda item: (-len(item["match_reasons"]), item["uid"]))
    payload = dict(project=project.model_dump(mode="json"), linked=sorted(linked),
                   facts=facts.model_dump(mode="json"),
                   plans=[item.model_dump(mode="json") for item in plans], papers=papers,
                   rule=RULE_VERSION)
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return dict(contract_version="local-radar-v1", project_id=project_id,
                rule_version=RULE_VERSION, input_fingerprint=fingerprint,
                items=matches[:50], total=len(matches),
                notice="只扫描本地论文库；名称或数据集匹配提示可能相关，不代表新论文推翻已有结论。")
