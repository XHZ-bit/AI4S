"""Replay recorded live candidates through storage; optionally validate one plan call.

Creates a new isolated database, never reads the user's paper library. The optional
call contains only the recorded approved sample and its synthetic project context.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import Settings  # noqa: E402
from app.db import projects as store  # noqa: E402
from app.db.sqlite import connect  # noqa: E402
from app.models.research import CandidateBundle, PaperLinkCreate, PlanBuildInput, PlanSaveRequest, ProjectConstraints, ResearchDecisionCreate, ResearchProjectCreate, SnapshotCreateRequest  # noqa: E402
from app.research import model_runtime, plan_provider, service  # noqa: E402
from app.research.planning import build_plan_draft  # noqa: E402


def replay(manifest_path, outputs_path, output, call_plan=False, recorded_plan=None):
    if not output.resolve().is_relative_to(ROOT / ".ui_validation") or output.exists():
        raise ValueError("Use a new workspace .ui_validation directory")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    recorded = json.loads(outputs_path.read_text(encoding="utf-8"))
    if recorded["manifest_sha256"] != hashlib.sha256(manifest_path.read_bytes()).hexdigest():
        raise ValueError("Inputs and outputs do not match")
    output.mkdir(parents=True)
    inputs = {request["id"]: request["input"] for request in manifest["requests"]}
    results = []
    selected = None
    conn = connect(str(output / "replay.sqlite3"))
    try:
        store.init_research_schema(conn)
        for record in recorded["results"]:
            if record["status"] != "candidate_output":
                results.append({"id": record["id"], "persisted": False, "reason": "recorded extraction failed"})
                continue
            source = inputs[record["id"]]
            project = store.create_project(conn, ResearchProjectCreate(title=f"[合成验收] {record['id']}", research_question="如何设计所选图像异常检测方法的首轮可复核实验？", domain="image_anomaly_detection", constraints=ProjectConstraints(objective="设计首轮实验：先补齐数据划分与评估协议，再核对计算资源和随机种子，条件明确后才设计小规模试验与结果记录。", version=1, notes=["全部资料来自原创合成验收文本，不代表真实科研结果。"])))
            document = source["document"]
            conn.execute("INSERT INTO papers(uid,title,abstract) VALUES(?,?,?)", (document["paper_uid"], record["id"], "Short approved excerpt"))
            conn.execute("INSERT INTO documents(id,paper_uid,content_hash,coverage) VALUES(?,?,?,?)", (document["document_id"], document["paper_uid"], document["content_hash"], "abstract"))
            passage = source["passages"][0]
            conn.execute("INSERT INTO passages(id,document_id,text,heading,kind,ordinal) VALUES(?,?,?,?,?,?)", (passage["id"], document["document_id"], passage["text"], passage["heading"], "text", 0))
            conn.commit()
            link = store.link_paper(conn, project.id, project.version, PaperLinkCreate(expected_project_version=project.version, paper_uid=document["paper_uid"], role="method"))
            bundle = CandidateBundle.model_validate(record["bundle"])
            bundle.project_id, bundle.paper_link_id, bundle.document_version = project.id, link.id, link.linked_document_version
            for evidence in bundle.evidence:
                evidence.document_version = link.linked_document_version
            for fact in [*bundle.methods, *bundle.experiment_settings, *bundle.measurements]:
                fact.project_id = project.id
                if hasattr(fact, "paper_link_id") and fact.paper_link_id is not None:
                    fact.paper_link_id = link.id
            store.save_candidate_bundle(conn, bundle)
            stored = store.list_facts(conn, project.id, paper_link_id=link.id)
            assert len(stored) == len(bundle.methods) + len(bundle.experiment_settings) + len(bundle.measurements)
            located = all(e.quote == passage["text"][e.locator.start_offset:e.locator.end_offset] for e in bundle.evidence)
            assert located
            results.append({"id": record["id"], "persisted": True, "facts": len(stored), "located_evidence": len(bundle.evidence), "all_quotes_exact": located, "warnings": bundle.warnings})
            if record["id"] == "result_ownership":
                selected = project.id, bundle

        report = {"scope": "recorded model outputs and isolated software integration; not independent human gold", "replays": results, "model_calls": 0, "human_reviewed": False}
        if call_plan or recorded_plan:
            if selected is None:
                raise ValueError("The approved synthetic ownership sample is required")
            project_id, bundle = selected
            method = next(m for m in bundle.methods if m.name == "CedarProbe")
            setting = next(s for s in bundle.experiment_settings if s.method_id == method.id)
            project = store.get_project(conn, project_id)
            decision = service.create_decision(conn, project_id, ResearchDecisionCreate(expected_project_version=project.version, selected_method_id=method.id, selected_experiment_setting_ids=[setting.id], rationale="合成验收人工选择：验证归属和未知条件，不比较真实性能", evidence_ids=method.field_evidence[0].evidence_ids))
            value = PlanBuildInput(project=project, decision=decision, methods=bundle.methods, experiment_settings=bundle.experiment_settings, measurements=bundle.measurements, evidence=bundle.evidence)
            captured = {}

            def capture(messages, **kwargs):
                captured.update(messages=messages, **kwargs)
                return '{"additional_steps":[]}'

            plan_provider.structured_chat = capture
            try:
                plan_provider.suggest_plan(value)
            except model_runtime.ResearchModelError:
                pass
            assert captured and len(json.dumps(captured, ensure_ascii=False).encode()) < 60000
            settings = Settings(_env_file=ROOT / ".env", access_mode="local", offline_mode=False,
                                llm_model=manifest["model"], llm_api_base=manifest["endpoint"], research_model_enabled=True,
                                research_model_response_format="json_schema", research_model_schema_require_all=False,
                                research_model_enable_thinking=False, research_model_max_requests=1,
                                research_model_max_output_tokens=8192, research_model_max_input_chars=60000,
                                research_model_timeout_seconds=60)
            if call_plan and not settings.dashscope_api_key.strip():
                raise ValueError("Model key not configured; no request sent")
            (output / "plan-request.json").write_text(json.dumps({"model": settings.llm_model, "endpoint": settings.llm_api_base, "max_requests": 1, "max_output_tokens": 8192, "enable_thinking": False, "response_format": "json_schema", "schema_require_all": False, **captured}, ensure_ascii=False, indent=2), encoding="utf-8")
            model_runtime.get_settings = lambda: settings

            class UsageLog(logging.Handler):
                def emit(self, record):
                    with (output / "transport.jsonl").open("a", encoding="utf-8") as handle:
                        handle.write(record.getMessage() + "\n")

            model_runtime.logger.addHandler(UsageLog())

            def live(messages, **kwargs):
                assert messages == captured["messages"]
                raw = recorded_plan.read_text(encoding="utf-8") if recorded_plan else model_runtime.structured_chat(messages, **kwargs)
                (output / "plan-raw.json").write_text(raw, encoding="utf-8")
                return raw

            plan_provider.structured_chat = live
            with model_runtime.model_call_scope("synthetic-plan-release-acceptance"):
                suggestions = plan_provider.suggest_plan(value)
            draft = build_plan_draft(value, suggestion_provider=lambda _: suggestions)
            saved = store.save_plan(conn, project_id, PlanSaveRequest(expected_project_version=project.version, expected_plan_version=0, plan=draft))
            snapshot = service.create_snapshot(conn, project_id, SnapshotCreateRequest(expected_project_version=project.version, plan_id=saved.id, plan_version=saved.version))
            (output / "plan-snapshot.json").write_bytes(service.snapshot_json(snapshot))
            report.update(model_calls=0 if recorded_plan else 1, plan_steps=len(saved.steps), model_steps=len(suggestions["additional_steps"]), snapshot_saved=True, plan_source=saved.source_kind.value,
                          replayed_plan_sha256=hashlib.sha256(recorded_plan.read_bytes()).hexdigest() if recorded_plan else None)
        (output / "acceptance.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False))
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--outputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--call-plan", action="store_true", help="One paid request, only after user authorization")
    parser.add_argument("--recorded-plan", type=Path, help="Replay an existing raw plan offline, without another model request")
    args = parser.parse_args()
    if args.call_plan and args.recorded_plan:
        parser.error("Choose a paid call or an offline replay, not both")
    replay(args.manifest, args.outputs, args.output, args.call_plan, args.recorded_plan)
