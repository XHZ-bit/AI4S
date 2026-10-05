"""Create an isolated synthetic Research Atlas database for browser validation.

The fixture is deliberately not a scientific result.  It never calls a model,
GROBID, Neo4j, or any network service.  The caller must choose a new or empty
output directory; production ``backend/data`` paths are rejected.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
PRODUCTION_DATA_DIR = (BACKEND_ROOT / "data").resolve()

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db import projects as store  # noqa: E402
from app.db import sqlite  # noqa: E402
from app.models.research import (  # noqa: E402
    CandidateBundle,
    EvidenceKind,
    EvidenceRef,
    ExperimentSetting,
    FieldEvidence,
    FindingStatus,
    Measurement,
    MethodCard,
    NumericValue,
    PaperLinkCreate,
    PlanSaveRequest,
    ProjectConstraints,
    ProtocolStep,
    ResearchDecisionCreate,
    ResearchProjectCreate,
    SnapshotCreateRequest,
    StatusTransitionRequest,
    ValidationPlan,
)
from app.research import service  # noqa: E402

FIXTURE_NOTICE = (
    "合成浏览器验收资料：所有论文、方法、条件和数值均为虚构界面夹具，"
    "不代表科研结论、真实性能或复现成功。"
)


def validate_output_directory(output_dir: Path) -> Path:
    """Resolve and validate the caller-owned isolated output directory."""

    target = output_dir.expanduser().resolve()
    if target == PRODUCTION_DATA_DIR or PRODUCTION_DATA_DIR in target.parents:
        raise ValueError("拒绝写入 backend/data 生产数据目录或其子目录")
    if target.exists():
        if not target.is_dir():
            raise ValueError("输出路径已存在且不是目录")
        if any(target.iterdir()):
            raise ValueError("输出目录已存在且非空；请选择新的隔离目录")
    return target


def _field_evidence(
    field_path: str,
    evidence_id: str,
    finding_status: FindingStatus = FindingStatus.REPORTED,
) -> FieldEvidence:
    return FieldEvidence(
        field_path=field_path,
        source_kind="literature_report",
        finding_status=finding_status,
        evidence_ids=[evidence_id]
        if finding_status in {FindingStatus.REPORTED, FindingStatus.CONFLICTING}
        else [],
        note=FIXTURE_NOTICE,
    )


def _seed_source_document(conn) -> tuple[str, str, str]:
    paper_uid = "synthetic-browser-paper-001"
    document_id = "synthetic-browser-document-001"
    passage_id = "synthetic-browser-passage-001"
    content_hash = "synthetic-browser-content-v1"
    passage = (
        "虚构资料，仅用于浏览器验收。SyntheticProbe 是一个不存在的占位方法。"
        "在合成设置甲记录界面检查值 0.41，在合成设置乙记录界面检查值 0.37；"
        "这些值不是科研性能、验收阈值或成功结论。设置乙未报告随机种子和计算资源。"
    )
    conn.execute(
        """INSERT INTO papers(
               uid,title,abstract,authors_json,year,venue,categories_json,source,parse_status
           ) VALUES(?,?,?,?,?,?,?,?,?)""",
        (
            paper_uid,
            "[合成夹具] SyntheticProbe 浏览器验收资料",
            FIXTURE_NOTICE,
            json.dumps(["Research Atlas Fixture"], ensure_ascii=False),
            2026,
            "Synthetic browser fixture",
            json.dumps(["synthetic"], ensure_ascii=False),
            "synthetic_fixture",
            "parsed",
        ),
    )
    conn.execute(
        """INSERT INTO documents(
               id,paper_uid,content_hash,coverage,filename,warnings_json
           ) VALUES(?,?,?,?,?,?)""",
        (
            document_id,
            paper_uid,
            content_hash,
            "fulltext",
            "synthetic-browser-fixture.txt",
            json.dumps([FIXTURE_NOTICE], ensure_ascii=False),
        ),
    )
    conn.execute(
        """INSERT INTO passages(
               id,document_id,heading,text,page,ordinal,kind,metadata_json
           ) VALUES(?,?,?,?,?,?,?,?)""",
        (
            passage_id,
            document_id,
            "合成实验条件",
            passage,
            1,
            0,
            "text",
            json.dumps({"synthetic_fixture": True}, ensure_ascii=False),
        ),
    )
    conn.commit()
    return paper_uid, document_id, passage_id


def prepare_fixture(output_dir: Path) -> dict[str, object]:
    """Create one complete browser-readable workflow in an isolated SQLite DB."""

    target = validate_output_directory(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    database_path = target / "atlas.db"
    conn = sqlite.connect(str(database_path))
    try:
        paper_uid, document_id, passage_id = _seed_source_document(conn)
        project = store.create_project(
            conn,
            ResearchProjectCreate(
                title="[合成验收] 图像异常检测首轮方案",
                research_question="如何验证工作台能区分同一方法的两个合成实验设置？",
                domain="image_anomaly_detection",
                constraints=ProjectConstraints(
                    version=1,
                    objective="仅验证浏览器工作流、版本冻结和依据追踪，不验证算法效果",
                    allowed_datasets=["SyntheticAD-Fixture"],
                    required_metrics=["fixture_check_value"],
                    notes=[FIXTURE_NOTICE, "计算资源、耗时与真实指标均保持未知。"],
                ),
            ),
        )
        link = store.link_paper(
            conn,
            project.id,
            project.version,
            PaperLinkCreate(
                expected_project_version=project.version,
                paper_uid=paper_uid,
                role="primary",
                note=FIXTURE_NOTICE,
            ),
        )
        project = store.get_project(conn, project.id)
        if project is None or link.linked_document_version is None:
            raise RuntimeError("fixture project or frozen document was not persisted")

        now = datetime.now(UTC)
        evidence_id = "evidence-synthetic-browser-001"
        method_id = "method-synthetic-probe"
        setting_a_id = "setting-synthetic-a"
        setting_b_id = "setting-synthetic-b"
        measurement_a_id = "measurement-synthetic-a"
        measurement_b_id = "measurement-synthetic-b"
        evidence = EvidenceRef(
            id=evidence_id,
            source_kind="literature_report",
            finding_status="reported",
            kind=EvidenceKind.TEXT,
            paper_uid=paper_uid,
            document_id=document_id,
            document_version=link.linked_document_version,
            passage_id=passage_id,
            quote=(
                "虚构资料，仅用于浏览器验收。SyntheticProbe 是一个不存在的占位方法。"
            ),
            note=FIXTURE_NOTICE,
            extraction_version="browser-fixture-v1",
        )
        method = MethodCard(
            id=method_id,
            project_id=project.id,
            version=1,
            source_kind="literature_report",
            finding_status="reported",
            field_evidence=[_field_evidence("name", evidence_id)],
            paper_link_id=link.id,
            name="SyntheticProbe（虚构占位方法）",
            task="浏览器验收",
            summary=FIXTURE_NOTICE,
            limitations=["不能用于推断真实算法效果", "未报告计算资源与运行耗时"],
            created_at=now,
            updated_at=now,
        )
        setting_a = ExperimentSetting(
            id=setting_a_id,
            project_id=project.id,
            version=1,
            source_kind="literature_report",
            finding_status="reported",
            field_evidence=[
                _field_evidence("dataset", evidence_id),
                _field_evidence("split", evidence_id),
                _field_evidence("evaluation_protocol", evidence_id),
                _field_evidence("resources", evidence_id, FindingStatus.UNKNOWN),
            ],
            paper_link_id=link.id,
            method_id=method_id,
            name="合成设置甲（图像级）",
            dataset="SyntheticAD-Fixture",
            dataset_version="fixture-v1",
            split="fixture-a",
            evaluation_protocol="仅检查界面中的图像级条件分组",
            resources=[],
            random_seed=None,
            notes=[FIXTURE_NOTICE, "资源和随机种子未知。"],
            created_at=now,
            updated_at=now,
        )
        setting_b = ExperimentSetting(
            id=setting_b_id,
            project_id=project.id,
            version=1,
            source_kind="literature_report",
            finding_status="reported",
            field_evidence=[
                _field_evidence("dataset", evidence_id),
                _field_evidence("split", evidence_id),
                _field_evidence("evaluation_protocol", evidence_id),
                _field_evidence("random_seed", evidence_id, FindingStatus.UNKNOWN),
                _field_evidence("resources", evidence_id, FindingStatus.UNKNOWN),
            ],
            paper_link_id=link.id,
            method_id=method_id,
            name="合成设置乙（像素级）",
            dataset="SyntheticAD-Fixture",
            dataset_version="fixture-v1",
            split="fixture-b",
            evaluation_protocol="仅检查界面中的像素级条件分组",
            resources=[],
            random_seed=None,
            notes=[FIXTURE_NOTICE, "随机种子和资源未报告，必须显示为未知。"],
            created_at=now,
            updated_at=now,
        )
        measurement_a = Measurement(
            id=measurement_a_id,
            project_id=project.id,
            version=1,
            source_kind="literature_report",
            finding_status="reported",
            field_evidence=[
                _field_evidence("metric_name", evidence_id),
                _field_evidence("metric_scope", evidence_id),
                _field_evidence("value", evidence_id),
            ],
            experiment_setting_id=setting_a_id,
            metric_name="fixture_check_value",
            metric_scope="image/browser_fixture_only",
            value=NumericValue(value=0.41, scale="raw"),
            created_at=now,
            updated_at=now,
        )
        measurement_b = Measurement(
            id=measurement_b_id,
            project_id=project.id,
            version=1,
            source_kind="literature_report",
            finding_status="reported",
            field_evidence=[
                _field_evidence("metric_name", evidence_id),
                _field_evidence("metric_scope", evidence_id),
                _field_evidence("value", evidence_id),
            ],
            experiment_setting_id=setting_b_id,
            metric_name="fixture_check_value",
            metric_scope="pixel/browser_fixture_only",
            value=NumericValue(value=0.37, scale="raw"),
            created_at=now,
            updated_at=now,
        )
        bundle = CandidateBundle(
            project_id=project.id,
            paper_link_id=link.id,
            document_id=document_id,
            document_version=link.linked_document_version,
            extraction_version="browser-fixture-v1",
            evidence=[evidence],
            methods=[method],
            experiment_settings=[setting_a, setting_b],
            measurements=[measurement_a, measurement_b],
            warnings=[FIXTURE_NOTICE],
        )
        store.save_candidate_bundle(conn, bundle)
        confirmed = []
        for fact in [method, setting_a, setting_b, measurement_a, measurement_b]:
            confirmed.append(
                store.transition_fact(
                    conn,
                    project.id,
                    fact.id,
                    StatusTransitionRequest(
                        expected_version=1,
                        from_status="candidate",
                        to_status="user_confirmed",
                        actor="synthetic-browser-fixture",
                        reason="人工验收夹具预置：仅确认记录适合检查界面，不确认科研真实性",
                    ),
                )
            )

        decision = service.create_decision(
            conn,
            project.id,
            ResearchDecisionCreate(
                expected_project_version=project.version,
                selected_method_id=method_id,
                selected_experiment_setting_ids=[setting_a_id],
                considered_candidate_ids=[setting_a_id, setting_b_id],
                rationale=(
                    "用户输入的合成决策：先查看设置甲，仅用于验证选择与历史展示；"
                    "不表示设置甲优于设置乙。"
                ),
                evidence_ids=[evidence_id],
            ),
        )
        manual_plan = ValidationPlan(
            project_id=project.id,
            version=1,
            title="[人工方案/合成] 浏览器首轮检查",
            objective="检查选择、保存、快照、导出和打印流程，不执行模型训练",
            hypothesis=None,
            selected_method_id=method_id,
            selected_experiment_setting_ids=[setting_a_id],
            assumptions=["本方案只验证产品交互与数据追踪"],
            unknowns=["真实显存需求未知", "真实运行耗时未知", "真实科研指标未知"],
            steps=[
                ProtocolStep(
                    id="step-browser-review",
                    title="核对合成记录与来源",
                    purpose="确认页面没有把虚构资料显示为真实科研结论",
                    inputs=[setting_a_id, measurement_a_id],
                    procedure=[
                        "查看方法、两个实验设置和来源片段。",
                        "确认未知资源与耗时没有被自动补全。",
                    ],
                    expected_observation="页面显示合成标识、未知项和可定位来源。",
                    acceptance_criteria=[
                        "设置甲与设置乙保持为两个独立设置",
                        "不出现真实训练或效果成功声明",
                    ],
                    evidence_ids=[evidence_id],
                )
            ],
            target_measurements=[measurement_a_id],
            risks=["误把合成界面检查值解释为真实科研性能"],
            source_kind="user_input",
        )
        plan = store.save_plan(
            conn,
            project.id,
            PlanSaveRequest(
                expected_project_version=project.version,
                expected_plan_version=0,
                plan=manual_plan,
            ),
        )
        snapshot = service.create_snapshot(
            conn,
            project.id,
            SnapshotCreateRequest(
                expected_project_version=project.version,
                plan_id=plan.id,
                plan_version=plan.version,
            ),
        )

        manifest: dict[str, object] = {
            "fixture_kind": "synthetic_browser_validation",
            "scientific_result": False,
            "external_calls_made": False,
            "notice": FIXTURE_NOTICE,
            "data_dir": str(target),
            "database_path": str(database_path),
            "project_id": project.id,
            "project_version": project.version,
            "paper_uid": paper_uid,
            "paper_link_id": link.id,
            "document_id": document_id,
            "evidence_id": evidence_id,
            "confirmed_fact_ids": [item.id for item in confirmed],
            "decision_id": decision.id,
            "plan_id": plan.id,
            "plan_version": plan.version,
            "plan_source_kind": plan.source_kind.value,
            "snapshot_id": snapshot.id,
            "snapshot_version": snapshot.snapshot_version,
            "snapshot_review_status": snapshot.review_status.value,
            "cleanup": (
                "关闭使用该目录的后端后，核对绝对路径并手工删除整个临时目录；"
                "脚本不会自动清理。"
            ),
        }
        (target / "browser-fixture.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return manifest
    finally:
        conn.close()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description="Create an isolated synthetic DB for Research Atlas browser validation."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="New or empty isolated DATA_DIR. backend/data and non-empty targets are refused.",
    )
    args = parser.parse_args()
    try:
        manifest = prepare_fixture(args.output_dir)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
