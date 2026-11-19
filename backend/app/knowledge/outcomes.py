"""Saved node notes and explicitly selected learning outcomes; never calls a model."""

from __future__ import annotations

import json
import re
from urllib.parse import urlencode

from fastapi import HTTPException

from app.knowledge import store

ORIGINS = {"source": "原文内容", "inference": "系统归纳", "user": "用户撰写或修订", "saved_ai_answer": "用户笔记（含所保存的 AI 回答，待核对）"}
SECTION_LABELS = {"overview": "直观理解", "definition": "定义", "derivation": "公式与推导", "prerequisites": "前置基础", "implementation": "实现", "limitations": "边界与限制"}


def _fenced(text, language="text"):
    """Keep saved code/input/output literal even when they contain Markdown fences."""
    fence = "`" * max(3, 1 + max((len(match[0]) for match in re.finditer(r"`+", text)), default=0))
    return [fence + language, text, fence]


def capture_note_references(conn, pid, references, previous):
    if not isinstance(references, list) or len(references) > 40:
        raise HTTPException(422, "每份笔记最多保留 40 条原文依据")
    captured = []
    previous_by_key = {(item.get('id'), item.get('source_version')): item
                       for item in (previous or {}).get('evidence_references', [])}
    for reference in references:
        if not isinstance(reference, dict) or not isinstance(reference.get('id'), str):
            raise HTTPException(422, "笔记依据需要有效的证据标识")
        key = (reference['id'], reference.get('source_version'))
        if key in previous_by_key:
            item = previous_by_key[key]
        else:
            matches = store.evidence(conn, pid, [reference['id']])
            if not matches:
                raise HTTPException(422, "笔记依据不属于当前研究空间")
            item = matches[0]
            if any(item.get(flag) for flag in ('source_missing', 'source_changed', 'unresolved')):
                raise HTTPException(409, "笔记依据已变化，请重新核对原文后选入")
            if reference.get('source_version') and item.get('source_version') != reference['source_version']:
                raise HTTPException(409, "回答引用的资料已更新，请重新核对后选入笔记")
        if not any(saved['id'] == item['id'] and saved.get('source_version') == item.get('source_version') for saved in captured):
            captured.append(item)
    return captured


def present_note(conn, pid, note):
    value = dict(note)
    context = json.loads(value.get('source_json') or '{}')
    references = []
    for captured in context.get('evidence_references', []):
        reference = dict(captured)
        matches = store.evidence(conn, pid, [reference['id']])
        live = matches[0] if matches else None
        reference['source_missing'] = not live or live.get('source_missing', False)
        reference['source_changed'] = bool(live and (live.get('source_changed') or live.get('source_version') != reference.get('source_version')))
        reference['unresolved'] = bool(not live or live.get('unresolved') or live.get('quote') != reference.get('quote') or live.get('block_id') != reference.get('block_id'))
        references.append(reference)
    value['context'] = {**context, 'evidence_references': references}
    return value


def validate_note_context(conn, pid, context, previous=None):
    if not pid:
        raise HTTPException(422, "节点笔记需要指定研究空间")
    store.init(conn)
    node = store.record(conn, "kw_nodes", pid, context["knowledge_node_id"])
    sid = context.get("source_id") or node["source_id"]
    if sid != node["source_id"]:
        raise HTTPException(422, "笔记来源与知识节点不一致")
    source = store.source(conn, pid, sid, blocks=True, include_removed=True)
    if context.get("block_id") and context["block_id"] not in {b["id"] for b in source["blocks"]}:
        # Previously captured context stays readable/editable after parsing changes.
        if not previous or any(context.get(k) != previous.get(k) for k in ("knowledge_node_id", "source_id", "block_id", "source_version")):
            raise HTTPException(422, "笔记片段不属于当前资料")
    same_context = bool(previous) and all(context.get(k) == previous.get(k) for k in ("knowledge_node_id", "source_id", "block_id", "source_version", "node_version"))
    if not same_context:
        if context.get("source_version") and context["source_version"] != source["version"]:
            raise HTTPException(409, "资料已更新，请重新选择笔记来源")
        if context.get("node_version") and context["node_version"] != node["version"]:
            raise HTTPException(409, "节点已更新，请刷新后保存笔记")
    references = capture_note_references(conn, pid, context.get('evidence_references') or [], previous)
    return {**context, "evidence_references": references, "source_id": sid, "source_version": context.get("source_version") or source["version"],
            "node_version": context.get("node_version") or node["version"], "content_origin": context.get("content_origin") or "user"}


def _has_table(conn, name):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def catalog(conn, pid, nid):
    from app.knowledge import comparison, learning
    from app.knowledge.learning_depth import safe_presentation, variant
    node = store.record(conn, "kw_nodes", pid, nid)
    source = store.source(conn, pid, node["source_id"], include_removed=True)
    notes = []
    for row in conn.execute("SELECT * FROM workspace_records WHERE project_id=? ORDER BY updated_at DESC,id", (pid,)):
        context = json.loads(row["source_json"] or "{}")
        if context.get("knowledge_node_id") != nid or str(row["id"]).startswith("editor:"):
            continue
        presented = present_note(conn, pid, row)
        references_changed = any(any(reference.get(flag) for flag in ('source_missing', 'source_changed', 'unresolved'))
                                 for reference in presented['context'].get('evidence_references', []))
        notes.append({**presented, "stale": source["removed"] or context.get("node_version") != node["version"] or context.get("source_version") != source["version"] or references_changed})
    lessons, lesson_variants, evidence_ids = [], set(), set(node.get("evidence_ids", []))
    for row in conn.execute("SELECT fingerprint,data FROM kw_learning WHERE project_id=? AND node_id=? ORDER BY rowid DESC", (pid, nid)):
        item = json.loads(row["data"])
        pair = variant(item)
        if pair in lesson_variants:
            continue
        lesson_variants.add(pair)
        presented = safe_presentation(item)
        sections = {key: value for key, value in presented.get("sections", {}).items() if key not in item.get("hidden_sections", []) and value and key in SECTION_LABELS}
        if not sections:
            continue
        lessons.append({"id": item["id"], "revision": item.get("revision", 1), "goal": pair[0], "sections": sections,
                        "user_edited_sections": item.get("user_edited_sections", []), "origin": item.get("origin", "inference"),
                        "stale": source["removed"] or row["fingerprint"] != learning.learning_fingerprint(conn, pid, nid, *pair)})
        evidence_ids.update(e["id"] for e in item.get("evidence", []) if e.get("id"))
    comparisons = []
    for item in comparison.list_comparisons(conn, pid):
        relevant = nid in item.get("focus_node_ids", []) or any(nid in entry.get("node_ids", []) for row in item.get("rows", []) for entry in row.get("values", []))
        if not relevant:
            continue
        cells = []
        for row in item.get("rows", []):
            for entry in row.get("values", []):
                cells.append({"dimension": row["dimension"], "compatibility": row.get("compatibility", ""), **entry})
                evidence_ids.update(entry.get("evidence_ids", []))
        comparisons.append({"id": item["id"], "revision": item.get("revision", 1), "stale": item.get("stale", False), "cells": cells, "evidence": item.get('evidence', [])})
    practices = []
    if _has_table(conn, "kw_practice"):
        for row in conn.execute("SELECT data FROM kw_practice WHERE project_id=? AND node_id=? ORDER BY rowid DESC", (pid, nid)):
            item = json.loads(row[0])
            runs = []
            if _has_table(conn, "kw_practice_runs"):
                runs = [json.loads(r[0]) for r in conn.execute(
                    "SELECT data FROM kw_practice_runs WHERE project_id=? AND practice_id=? ORDER BY rowid DESC",
                    (pid, item["id"]),
                )]
            run_defaults = {"status": "", "created_at": "", "checked": False, "passed": None,
                            "prediction": "", "output": None, "explanation": "", "mapping_id": None,
                            "mapping_revision": None, "mapping_snapshot": None,
                            "practice_id": item["id"], "practice_revision": None,
                            "node_version": None, "source_version": None, "practice_fingerprint": None,
                            "code": None, "input_json": None, "elapsed_ms": None}
            mapping_stale = False
            if item.get('mapping_id'):
                from app.knowledge.practice import selected_mapping
                try:
                    selected_mapping(conn, pid, nid, item['mapping_id'], item.get('mapping_revision'))
                except HTTPException:
                    mapping_stale = True
            practices.append({"id": item["id"], "title": item["title"], "goal": item.get("goal", ""), "revision": item.get("revision", 1),
                              "mapping_snapshot": item.get('mapping_snapshot'),
                              "stale": source["removed"] or item.get("node_version") != node["version"] or item.get("source_version") != source["version"] or mapping_stale,
                              "runs": [{"id": r["id"], **{key: r.get(key, default) for key, default in run_defaults.items()}} for r in runs]})
    from app.knowledge.implementations import list_mappings
    mappings = list_mappings(conn, pid, nid)
    return {"node": {"id": nid, "label": node["label"], "version": node["version"]}, "source": {"id": source["id"], "title": source["title"], "version": source["version"], "removed": source["removed"]},
            "notes": notes, "lessons": lessons, "evidence": store.evidence(conn, pid, sorted(evidence_ids)), "practices": practices, "comparisons": comparisons, "mappings": mappings}


def preview(conn, pid, nid, selection):
    data = catalog(conn, pid, nid)
    node, source = data["node"], data["source"]
    lines = ["# " + node["label"] + " · 学习笔记", "", "来源资料：" + source["title"], "", "本文件由用户选择的已保存内容整理；核对状态不代表科学结论保证。"]
    selected_count = 0

    def select(items, identity):
        found = next((item for item in items if item["id"] == identity), None)
        if not found:
            raise HTTPException(422, "所选成果不属于当前节点或已不可用，请刷新导出选项")
        return found

    def stale(item):
        if item.get("stale"):
            lines.extend(["", "> 此内容对应历史版本，来源或知识已变化，请重新核对。"])

    def append_mapping_evidence(label, evidence):
        if not evidence:
            return
        loc = evidence.get("locator") or {}
        position = " · ".join(str(part) for part in (
            "第 " + str(loc['page']) + " 页" if loc.get('page') else None,
            loc.get('heading'), loc.get('path')) if part) or "位置未确认"
        if loc.get("start_line"):
            position += " · 行 " + str(loc["start_line"])
            if loc.get("end_line") and loc["end_line"] != loc["start_line"]:
                position += "–" + str(loc["end_line"])
        lines.extend(["", label + "：" + str(evidence.get("source_title", "")) + " · " + position])
        if loc.get("commit"):
            lines.append("提交版本：" + str(loc["commit"]))
        if loc.get("url"):
            lines.append("来源地址：" + str(loc["url"]))
        if evidence.get("source_version"):
            lines.append("来源版本：" + str(evidence["source_version"]))
        lines.extend(["", evidence.get("quote", "")])

    def run_snapshot(run):
        snapshot = run.get("mapping_snapshot")
        if not snapshot:
            if run.get("mapping_id"):
                lines.extend(["", "运行时映射快照未保存。"])
            return
        lines.extend([
            "", "运行时映射快照（与当前映射可能不同）：", "",
            "修订：" + str(snapshot.get("revision", "未知")) + "；状态：" + str(snapshot.get("status", "未知"))
            + "；类型：" + str(snapshot.get("implementation_kind", "未知")), "",
            "核对者：" + str(snapshot.get("reviewed_by") or "未记录")
            + "；核对时间：" + str(snapshot.get("reviewed_at") or "未记录"), "",
            "来源版本：" + json.dumps(snapshot.get("source_versions", {}), ensure_ascii=False), "",
            "论文片段：" + str(snapshot.get("paper_span", "")), "",
            "代码片段：" + str(snapshot.get("code_span", "")), "",
            "映射说明：" + str(snapshot.get("explanation", "")),
        ])
        for label, evidence in (("论文依据", snapshot.get("paper_evidence")), ("代码依据", snapshot.get("code_evidence"))):
            append_mapping_evidence(label, evidence)

    def append_run(run, heading="### 教学运行："):
        status = {"success": "运行完成", "error": "运行出错", "timeout": "运行超时", "cancelled": "已停止"}.get(run["status"], run["status"] or "未记录")
        verdict = "用例通过" if run["checked"] and run["passed"] is True else "用例未通过" if run["checked"] and run["passed"] is False else "未进行用例判定"
        lines.extend([
            "", heading + run["id"], "",
            "运行时间：" + (run["created_at"] or "未记录"), "",
            "状态：" + status + "；" + verdict, "",
            "耗时：" + (str(run["elapsed_ms"]) + " ms" if run["elapsed_ms"] is not None else "未记录"), "",
            "练习版本标识：" + str(run["practice_id"]), "",
            "运行所关联的练习修订：" + str(run["practice_revision"] if run["practice_revision"] is not None else "未记录"), "",
            "运行所关联的节点版本：" + str(run["node_version"] if run["node_version"] is not None else "未记录")
            + "；来源版本：" + str(run["source_version"] if run["source_version"] is not None else "未记录"), "",
            "运行所关联的练习指纹：" + str(run["practice_fingerprint"] if run["practice_fingerprint"] is not None else "未记录"), "",
            "浏览器报告的教学运行，未独立验证。",
        ])
        if run.get("mapping_id"):
            lines.extend(["", "映射：" + run["mapping_id"] + " · 修订 " + str(run.get("mapping_revision") or "未记录")])
        for label, key, language in (("本次执行的 Python 代码", "code", "python"), ("本次执行的 JSON 输入", "input_json", "json")):
            lines.extend(["", label + "：", ""])
            if isinstance(run.get(key), str):
                lines.extend(_fenced(run[key], language))
            else:
                lines.append("旧运行未保存此项，不使用当前编辑稿补写。")
        for label, key in (("运行前预测", "prediction"), ("实际输出", "output"), ("用户解释", "explanation")):
            lines.extend(["", label + "：", ""])
            text = run.get(key)
            if isinstance(text, str) and text:
                lines.extend(_fenced(text))
            else:
                lines.append(("旧运行未保存输出。" if text is None else "无标准输出。") if key == "output" else "未填写")
        run_snapshot(run)

    for identity in selection.get("note_ids", []):
        note = select(data["notes"], identity)
        lines.extend(["", "## " + note["title"], "", "性质：" + ORIGINS.get(note["context"].get("content_origin", "user"), "用户笔记"), "", note["body"]])
        lines.extend(["", "笔记所关联的节点版本：" + str(note["context"].get("node_version", "未知")) + "；来源版本：" + str(note["context"].get("source_version", "未知"))])
        if note["context"].get("unresolved_questions"):
            lines.extend(["", "### 未解决问题", "", note["context"]["unresolved_questions"]])
        for evidence in note['context'].get('evidence_references', []):
            append_mapping_evidence('笔记所保存的原文依据', evidence)
            link = '/research/' + pid + '?' + urlencode({'view': 'reading', 'source': evidence['source_id'], 'block': evidence['block_id']})
            lines.extend(['', '平台定位：' + link])
        stale(note)
        selected_count += 1
    for identity in selection.get("evidence_ids", []):
        evidence = select(data["evidence"], identity)
        loc = evidence.get("locator", {})
        position = " · ".join(str(x) for x in ["第 " + str(loc["page"]) + " 页" if loc.get("page") else None, loc.get("heading"), loc.get("path"), "第 " + str(loc["start_line"]) + " 行" if loc.get("start_line") else None] if x)
        link = "/research/" + pid + "?" + urlencode({"view": "reading", "source": evidence["source_id"], "block": evidence["block_id"], **({"page": loc["page"]} if loc.get("page") else {})})
        lines.extend(["", "## 原文依据", "", (evidence.get("source_title") or source["title"]) + (" · " + position if position else " · 原文位置未确认"), "", "性质：原文片段；来源版本 " + str(evidence.get("source_version", "未知")), "", evidence.get("quote", ""), "", "平台定位：" + link])
        stale({"stale": any(evidence.get(k) for k in ("source_changed", "source_missing", "unresolved"))})
        selected_count += 1
    for chosen in selection.get("learning_sections", []):
        lesson = select(data["lessons"], chosen["artifact_id"])
        if lesson["revision"] != chosen["revision"]:
            raise HTTPException(409, "讲解已有修订，请刷新后重新选择导出")
        key = chosen["section"]
        if key not in lesson["sections"]:
            raise HTTPException(422, "所选讲解章节不可用")
        origin = "人工修订" if key in lesson["user_edited_sections"] else "系统讲解（需结合原文核对）"
        lines.extend(["", "## " + SECTION_LABELS[key], "", "性质：" + origin + "；修订 " + str(lesson["revision"]), "", lesson["sections"][key]])
        stale(lesson)
        selected_count += 1
    for identity in selection.get("practice_ids", []):
        item = select(data["practices"], identity)
        lines.extend(["", "## 练习记录：" + item["title"], "", item["goal"], "", "当前练习修订：" + str(item["revision"])])
        if item.get('mapping_snapshot'):
            lines.extend(['', '生成练习时所选的对应关系'])
            run_snapshot({'mapping_snapshot': item['mapping_snapshot']})
        for run in item["runs"]:
            append_run(run)
        if not item["runs"]:
            lines.extend(["", "尚无已保存的运行记录。"])
        stale(item)
        selected_count += 1
    for chosen in selection.get("mappings", []):
        item = select(data["mappings"], chosen["id"])
        if item["revision"] != chosen["revision"]:
            raise HTTPException(409, "映射已有修订，请刷新后重新选择导出")
        lines.extend([
            "", "## 论文与代码映射", "",
            "修订：" + str(item["revision"]) + "；状态：" + str(item.get("status", "未知"))
            + "；类型：" + str(item.get("implementation_kind", "未知")), "",
            "核对者：" + str(item.get("reviewed_by") or "未记录")
            + "；核对时间：" + str(item.get("reviewed_at") or "未记录"), "",
            "来源版本：" + json.dumps(item.get("source_versions", {}), ensure_ascii=False), "",
            "论文片段：" + str(item.get("paper_span", "")), "",
            "代码片段：" + str(item.get("code_span", "")), "", "说明：" + str(item.get("explanation", "")),
        ])
        for label, evidence in (("论文依据", item.get("paper_evidence")), ("代码依据", item.get("code_evidence"))):
            append_mapping_evidence(label, evidence)
        stale(item)
        for exercise in data["practices"]:
            for run in exercise["runs"]:
                if run.get("mapping_id") != item["id"]:
                    continue
                append_run(run, "### 关联教学运行：")
        selected_count += 1
    for chosen in selection.get("comparison_cells", []):
        item = select(data["comparisons"], chosen["comparison_id"])
        if item["revision"] != chosen["revision"]:
            raise HTTPException(409, "比较已有修订，请刷新后重新选择导出")
        cell = next((c for c in item["cells"] if c["dimension"] == chosen["dimension"] and c["source_id"] == chosen["source_id"]), None)
        if not cell:
            raise HTTPException(422, "比较单元格不存在")
        cell_source = store.source(conn, pid, cell["source_id"], include_removed=True)
        lines.extend(["", "## 方法比较：" + cell["dimension"], "", "资料：" + cell_source["title"], "", "性质：" + ORIGINS.get(cell.get("origin"), "系统归纳"), "", cell.get("text", ""), "", "比较条件：" + (cell.get("compatibility") or "未确认")])
        captured_evidence = cell.get('evidence_snapshot')
        if captured_evidence is None:
            comparison_evidence = {e['id']: e for e in item.get('evidence', [])}
            captured_evidence = [comparison_evidence[eid] for eid in cell.get('evidence_ids', []) if eid in comparison_evidence]
        for evidence in captured_evidence:
            append_mapping_evidence('比较保存时的依据', evidence)
        stale(item)
        selected_count += 1
    if not selected_count:
        raise HTTPException(422, "请至少选择一项已保存内容")
    return {"filename": "paperstride-learning-note.md", "markdown": "\n".join(lines) + "\n", "selected_count": selected_count}
