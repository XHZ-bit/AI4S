"""Deterministic analysis over versioned SQLite data. No external calls or writes."""
import hashlib
import json
from app.assistant.models import Action, Exercise, Reference, Report, Resource, Target
from app.db import projects as store
from app.db.sqlite import get_paper
from app.db.workspace import document_view, get_state
from app.research.constraints import evaluate_constraints
from app.research.service import project_facts


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def action(key, title, reason, impact, scope, identity, view, priority=2, refs=None, focus=None):
    return Action(id=key, title=title, reason=reason, impact=impact, priority=priority,
                  target=Target(scope=scope, id=identity, view=view, focus=focus), references=refs or [])


def project_input(conn, identity):
    project = store.get_project(conn, identity)
    if project is None:
        raise store.NotFoundError("课题不存在")
    facts = project_facts(conn, identity)
    links = store.list_paper_links(conn, identity)
    plans = store.list_plans(conn, identity)
    snapshots = store.list_snapshots(conn, identity)
    documents = [dict(r) for r in conn.execute(
        "SELECT id,content_hash,coverage FROM documents WHERE paper_uid IN (SELECT DISTINCT paper_uid FROM research_paper_link_versions WHERE project_id=?) ORDER BY id", (identity,))]
    inputs = {"project": project.model_dump(mode="json"), "facts": facts.model_dump(mode="json"),
              "links": [x.model_dump(mode="json") for x in links], "documents": documents,
              "plans": [x.model_dump(mode="json") for x in plans],
              "snapshots": [x.model_dump(mode="json") for x in snapshots], "rules": "atlas-actions-1"}
    return project, facts, links, plans, snapshots, fingerprint(inputs)


def project_report(conn, identity):
    project, facts, links, plans, snapshots, digest = project_input(conn, identity)
    live_links = {x.id for x in links if x.status == "active"}
    live_methods = [m for m in facts.methods if not m.paper_link_id or m.paper_link_id in live_links]
    settings = [s for s in facts.experiment_settings if not s.paper_link_id or s.paper_link_id in live_links]
    candidates = evaluate_constraints(project, live_methods, settings, facts.measurements)
    actions = []
    evidence = {x.id: x for x in facts.evidence}
    passages = {r["id"]: (r["document_id"], r["paper_uid"]) for r in conn.execute(
        "SELECT p.id,p.document_id,d.paper_uid FROM passages p JOIN documents d ON p.document_id=d.id WHERE d.paper_uid IN "
        "(SELECT paper_uid FROM research_paper_link_versions WHERE project_id=?)", (identity,))}
    if not live_links:
        actions.append(action("add-paper", "为课题关联资料", "当前没有有效论文关联", "方法和实验设置缺少资料输入", "project", identity, "evidence", 1))
    all_facts = [*facts.methods, *settings, *facts.measurements]
    covered, total = 0, 0
    for fact in all_facts:
        if fact.status == "withdrawn":
            continue
        refs = [Reference(kind="fact", id=fact.id)]
        for field in fact.field_evidence:
            total += 1
            valid = [eid for eid in field.evidence_ids if eid in evidence]
            if valid:
                covered += 1
            for eid in field.evidence_ids:
                ev = evidence.get(eid)
                if ev is None or (ev.passage_id and passages.get(ev.passage_id) != (ev.document_id, ev.paper_uid)):
                    actions.append(action(f"invalid:{fact.id}:{field.field_path}:{eid}", "修复失效的来源引用", f"{field.field_path} 的证据不可读取", "引用无法回到原文", "project", identity, "evidence", 0, refs, fact.id))
            if field.finding_status in {"conflicting", "not_parsed", "not_found", "unknown"}:
                actions.append(action(f"field:{fact.id}:{field.field_path}", f"补齐 {field.field_path}", f"字段状态：{field.finding_status.value}", "该字段不足以支持同条件判断", "project", identity, "evidence", 2,
                                      refs + [Reference(kind="evidence", id=eid) for eid in valid], fact.id))
        if hasattr(fact, "dataset"):
            for attr, label in (("dataset", "数据集"), ("split", "数据划分"), ("evaluation_protocol", "评估协议")):
                if not getattr(fact, attr):
                    actions.append(action(f"missing:{fact.id}:{attr}", f"定位{label}依据", f"{fact.name} 未提供{label}", "无法证明实验条件一致", "project", identity, "evidence", 2, refs, fact.id))
    for item in candidates:
        for check in item.checks:
            if check.status in {"unknown", "conflict"}:
                actions.append(action(f"constraint:{item.id}:{check.dimension}", f"{item.label} · {check.dimension}", check.reason,
                                      "约束存在冲突" if check.status == "conflict" else "资料不足，不能判断适配性", "project", identity, "scenarios",
                                      1 if check.status == "conflict" else 2, check.references, item.id))
    for plan in plans:
        for step in plan.steps:
            if not step.inputs or not step.acceptance_criteria:
                actions.append(action(f"step:{plan.id}:{step.id}", f"完善步骤：{step.title or '未命名'}", "缺少输入或验收标准", "执行后难以判断完成情况", "project", identity, "plans", 2, focus=step.id))
        if plan.review_status == "needs_review":
            actions.append(action(f"plan:{plan.id}", "查看方案依据变化", "；".join(plan.review_reasons), "已有方案的输入已发生变化", "project", identity, "changes", 1))
    for snapshot in snapshots:
        if snapshot.review_status == "needs_review":
            actions.append(action(f"snapshot:{snapshot.id}", "追踪快照影响范围", "；".join(snapshot.review_reasons), "旧成果保留，但引用依据已变化", "project", identity, "changes", 1, [Reference(kind="snapshot", id=snapshot.id)], snapshot.id))
    return Report(input_fingerprint=digest, candidates=candidates,
                  actions=sorted(actions, key=lambda a: (a.priority, a.id)),
                  coverage={"fields": total, "bound_fields": covered, "candidates": len(candidates), "issues": len(actions)})


def paper_report(conn, uid):
    paper = get_paper(conn, uid)
    if paper is None:
        raise store.NotFoundError("论文不存在")
    docs, saved = document_view(conn, uid), get_state(conn, uid)
    actions = []
    if not docs or not docs[0]["passages"]:
        actions.append(action("parse", "准备可阅读原文", "尚无解析后的正文片段", "无法定位章节依据", "paper", uid, "reading", 0))
    else:
        doc = docs[0]
        if doc["coverage"] != "fulltext":
            actions.append(action("fulltext", "补充全文资料", "目前只有摘要级覆盖", "实验条件与限制可能缺失", "paper", uid, "reading", 1))
        for p in doc["passages"]:
            if not saved["state"]["reading"].get(f"read:{p['id']}"):
                actions.append(action(f"read:{p['id']}", f"继续阅读：{p['heading']}", "尚未记录阅读此片段", "为理解方法建立原文上下文", "paper", uid, "reading", 3,
                                      [Reference(kind="passage", id=p["id"], paper_uid=uid, document_id=doc["id"], document_version=doc["content_hash"], page=p["page"], quote=p["text"])], p["id"]))
    for key, label in (("problem", "研究问题"), ("method", "输入与方法"), ("evidence", "实验依据"), ("limits", "方法限制")):
        if saved["state"]["answers"].get(key, {}).get("status") != "answered":
            actions.append(action(f"answer:{key}", f"梳理{label}", "尚未保存此项理解回答", "回答状态只记录学习进度", "paper", uid, "reading", 2, focus=key))
    for exp in saved["state"]["experiments"]:
        if exp.get("status") in {"failed", "error"}:
            actions.append(action(f"experiment:{exp.get('id', 'latest')}", "定位实验失败原因", "实验记录标记为失败", "先查看环境、配置和日志再尝试", "paper", uid, "experiment", 0))
    return Report(input_fingerprint=fingerprint([paper, docs, saved, "paper-coach-1"]),
                  actions=sorted(actions, key=lambda a: (a.priority, a.id))[:3], coverage={"passages": sum(len(d["passages"]) for d in docs)})


def exercises(session):
    from app.cases.catalog import SOURCES
    seed = int(fingerprint([session["id"], session["case_version"]])[:8], 16)
    params = {"B": 1 + seed % 4, "To": 2 + seed % 4, "Do": 20, "Ta": 3 + seed % 5, "Da": 2}
    source = SOURCES["files"][0]
    def reference(needle):
        line = next((i for i, text in enumerate(source["text"].splitlines(), 1) if needle in text), None)
        return [Reference(kind="source", id=source["path"], line=line)]
    result = []
    for identity, prompt in (("observation-v1", "给定以下参数，填写观测张量 [B, To, Do]"), ("action-v1", "给定以下参数，填写动作张量 [B, Ta, Da]")):
        result.append(Exercise(id=identity, kind="shape", prompt=prompt, parameters=params, references=reference("obs: B,To,Do" if identity == "observation-v1" else "action: B,Ta,Da"),
                               result=session["state"].get("practice", {}).get(identity)))
    result.append(Exercise(id="windows-v1", kind="choice", prompt="观测步数 To 和动作步数 Ta 是否必须相同？",
                          options=["必须相同", "不必相同，它们表示不同的窗口", "它们都是动作维度"], references=reference("To = 3"),
                          result=session["state"].get("practice", {}).get("windows-v1")))
    return result


def grade(session, identity, answer):
    exercise = next((e for e in exercises(session) if e.id == identity), None)
    if exercise is None:
        raise ValueError("练习不存在")
    p = exercise.parameters
    if exercise.kind == "shape":
        if answer.shape is None or answer.choice is not None:
            raise ValueError("请提交三个整数构成的形状")
        expected = [p["B"], p["To"], p["Do"]] if identity == "observation-v1" else [p["B"], p["Ta"], p["Da"]]
        correct, observed = answer.shape == expected, answer.shape
        explanation = "固定接口的维度顺序：" + ("B, To, Do" if identity == "observation-v1" else "B, Ta, Da") + f"；本题为 {expected}。"
    else:
        if answer.choice is None or answer.shape is not None:
            raise ValueError("请提交选项")
        correct, observed = answer.choice == 1, answer.choice
        explanation = "源码示意 To=3、Ta=4、T=6；观测窗口与动作窗口作用不同。"
    old = session["state"].get("practice", {}).get(identity, {})
    if old.get("answer") == observed:
        return old
    return {"answer": observed, "correct": correct, "attempts": old.get("attempts", 0) + 1, "explanation": explanation}


def case_report(session):
    from app.cases.catalog import QUESTIONS, STEP_IDS
    identity = "diffusion-policy-intro"
    actions = []
    if session["stale"]:
        actions.append(action("stale", "新建当前版本学习记录", "当前会话对应旧版专题", "历史仍可阅读与导出", "case", identity, "learn", 0))
    if session["runs"] and not session["runs"][0]["report"]["passed"]:
        failed = [c["label"] for c in session["runs"][0]["report"]["checks"] if not c["passed"]]
        actions.append(action("run-failed", "修复源码检查问题", "、".join(failed), "查看检查明细，保留历史后重新运行", "case", identity, "learn", 0, focus="inspect"))
    for q in QUESTIONS:
        a = session["state"]["answers"].get(q["id"])
        if not a or not a.get("correct"):
            actions.append(action(q["id"], "回顾：" + q["question"], "上次回答有误" if a else "尚未作答", "对照对应源码后再次回答", "case", identity, "learn", 1 if a else 2, focus=q["step"]))
    practice = exercises(session)
    for e in practice:
        if not e.result or not e.result["correct"]:
            actions.append(action(e.id, "练习：" + e.prompt, "上次练习有误" if e.result else "将接口知识应用到一组新参数", "观察形状再作答", "case", identity, "animation", 1 if e.result else 2, e.references, e.id))
    for step in STEP_IDS:
        if step not in session["state"]["read_steps"]:
            actions.append(action(f"step:{step}", "继续源码学习", "此步骤尚未记录读过", "按任务逐步理解接口与配置", "case", identity, "learn", 4, focus=step))
    return Report(input_fingerprint=fingerprint(session), actions=sorted(actions, key=lambda a: (a.priority, a.id))[:3], exercises=practice,
                  coverage={"read": len(session["state"]["read_steps"]), "answered": len(session["state"]["answers"]),
                            "practice_correct": sum(bool(e.result and e.result["correct"]) for e in practice)})


def resource_list(conn, scope, identity):
    resources = []
    if scope == "case":
        from app.api.cases import require_case
        from app.cases.catalog import SOURCES, VERSION
        require_case(identity)
        for f in SOURCES["files"]:
            resources.append(Resource(id=f["path"], kind="source", title=f["path"], origin="source_repo", version=SOURCES["commit"], text=f["text"], url=f["url"], line=1, tasks=["接口定位", "配置检查", "练习回顾"]))
        for key, title in (("tensor", "张量形状推演"), ("windows", "观测与动作窗口")):
            resources.append(Resource(id=key, kind="animation", title=title, origin="illustrative", version=VERSION, tasks=["参数推演", "自动练习"]))
        return resources
    if scope == "project":
        project, _, links, _, _, _ = project_input(conn, identity)
        uids = sorted({link.paper_uid for link in links if link.status == "active"})
    else:
        if get_paper(conn, identity) is None:
            raise store.NotFoundError("论文不存在")
        uids = [identity]
    for uid in uids:
        paper = get_paper(conn, uid)
        for doc in document_view(conn, uid):
            resources.append(Resource(id=doc["id"], kind="pdf", title=paper["title"], origin="literature", version=doc["content_hash"],
                                      paper_uid=uid, document_id=doc["id"], url=f"/api/papers/{uid}/documents/{doc['id']}/file",
                                      passages=[{"id": p["id"], "heading": p["heading"], "text": p["text"], "page": p["page"]} for p in doc["passages"]], tasks=["原文阅读", "引用追溯"]))
    resources.append(Resource(id="evidence-chain", kind="diagram", title="从资料到研究行动", origin="illustrative", version="1"))
    return resources


def snapshot_state(conn, project_id, snapshot):
    prow = conn.execute("SELECT payload_json FROM research_project_versions WHERE project_id=? AND version=?", (project_id, snapshot.frozen_project_version)).fetchone()
    facts = {}
    missing = []
    for ref in snapshot.frozen_facts:
        row = conn.execute("SELECT payload_json FROM research_fact_versions WHERE project_id=? AND fact_id=? AND version=?", (project_id, ref.id, ref.version)).fetchone()
        if row:
            facts[ref.id] = json.loads(row["payload_json"])
        else:
            missing.append(ref.id)
    decision = conn.execute("SELECT payload_json FROM research_decision_versions WHERE project_id=? AND decision_id=? AND version=?", (project_id, snapshot.frozen_decision.id, snapshot.frozen_decision.version)).fetchone()
    if not prow:
        missing.append("project")
    if not decision:
        missing.append("decision")
    return {"project": json.loads(prow["payload_json"]) if prow else None, "facts": facts,
            "decision": json.loads(decision["payload_json"]) if decision else None,
            "documents": {d.paper_link_id: d.model_dump(mode="json") for d in snapshot.frozen_documents},
            "plan": snapshot.plan.model_dump(mode="json")}, missing


def diff_snapshots(conn, identity, sid, against):
    original = store.get_snapshot(conn, identity, sid)
    if original is None:
        raise store.NotFoundError("快照不存在")
    before, missing = snapshot_state(conn, identity, original)
    if against == "current":
        project, facts, links, plans, _, digest = project_input(conn, identity)
        all_facts = [*facts.methods, *facts.experiment_settings, *facts.measurements]
        current_plan = next((p for p in plans if p.id == original.plan.id), None)
        decisions = store.list_decisions(conn, identity)
        decision = next((d for d in decisions if d.status == "active"), None)
        after = {"project": project.model_dump(mode="json"), "facts": {f.id: f.model_dump(mode="json") for f in all_facts},
                 "documents": {link.id: {"paper_link_id": link.id, "paper_uid": link.paper_uid, "document_id": link.linked_document_id, "document_version": link.linked_document_version} for link in links if link.status == "active"},
                 "plan": current_plan.model_dump(mode="json") if current_plan else None,
                 "decision": decision.model_dump(mode="json") if decision else None}
        # Compare the same document fields; hashes are resolved from current documents.
        for d in after["documents"].values():
            row = conn.execute("SELECT content_hash FROM documents WHERE id=?", (d["document_id"],)).fetchone()
            d["content_hash"] = row["content_hash"] if row else None
    else:
        other = store.get_snapshot(conn, identity, against)
        if other is None:
            raise store.NotFoundError("对比快照不存在或不属于当前课题")
        after, other_missing = snapshot_state(conn, identity, other)
        missing += other_missing
        digest = fingerprint([before, after])
    changes = []

    def visit(a, b, path):
        if isinstance(a, dict) and isinstance(b, dict):
            for key in sorted(set(a) | set(b)):
                if key not in {"created_at", "updated_at"}:
                    visit(a.get(key), b.get(key), f"{path}.{key}" if path else key)
        elif path == "plan.steps" and isinstance(a, list) and isinstance(b, list):
            visit({step["id"]: step for step in a}, {step["id"]: step for step in b}, path)
            if [step["id"] for step in a] != [step["id"] for step in b]:
                changes.append({"path": "plan.steps.order", "before": [s["id"] for s in a], "after": [s["id"] for s in b], "kind": "changed"})
        elif a != b:
            changes.append({"path": path, "before": a, "after": b, "kind": "added" if a is None else "removed" if b is None else "changed"})
    visit(before, after, "")
    changed_fact_ids = {c["path"].split(".")[1] for c in changes if c["path"].startswith("facts.")}
    affected = []
    for snap in store.list_snapshots(conn, identity):
        used = {f.id for f in snap.frozen_facts} & changed_fact_ids
        plan_changed = snap.plan.id == original.plan.id and any(c["path"].startswith("plan.") for c in changes)
        if used or plan_changed or any(c["path"].startswith(("project.constraints", "documents.", "decision.")) for c in changes):
            affected.append({"snapshot_id": snap.id, "plan_id": snap.plan.id, "fact_ids": sorted(used),
                             "step_ids": [s.id for s in snap.plan.steps], "reason": "引用依赖变化；不表示科学结论已被推翻"})
    return {"contract_version": "assistant-v1", "input_fingerprint": digest, "snapshot_id": sid, "against": against,
            "changes": changes, "affected": affected, "unresolved": sorted(set(missing))}
