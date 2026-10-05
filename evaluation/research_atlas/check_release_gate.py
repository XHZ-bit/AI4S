"""Static preflight for the T0 integration points required by T6 acceptance."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]

    checks = []

    def text_contains(relative: str, needles: tuple[str, ...], check_id: str) -> None:
        path = root / relative
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        missing = [needle for needle in needles if needle not in text]
        checks.append(
            {
                "check_id": check_id,
                "passed": path.exists() and not missing,
                "path": relative,
                "missing_markers": missing,
            }
        )

    def files_exist(check_id: str, relatives: tuple[str, ...]) -> None:
        missing = [relative for relative in relatives if not (root / relative).exists()]
        checks.append(
            {
                "check_id": check_id,
                "passed": not missing,
                "paths": list(relatives),
                "missing_paths": missing,
            }
        )

    text_contains(
        "backend/app/main.py",
        ("app.api.projects", "include_router"),
        "projects_router_registered",
    )
    text_contains(
        "backend/app/db/sqlite.py",
        ("init_research_schema", "interrupt_incomplete_tasks"),
        "research_schema_and_restart_interrupt_wired",
    )
    text_contains(
        "backend/app/jobs.py",
        ("run_research_task",),
        "research_task_runner_wired",
    )
    files_exist(
        "t2_t1_adapter_available",
        ("backend/app/research/extraction.py",),
    )
    files_exist(
        "t5_projection_and_query_available",
        (
            "backend/app/research/graph_projection.py",
            "backend/app/research/graph_queries.py",
            "docs/parallel-dev/handoffs/T5.md",
        ),
    )
    text_contains(
        "frontend/src/App.tsx",
        ("/research", "ResearchProjectsPage", "ResearchProjectPage"),
        "research_frontend_routes_registered",
    )
    text_contains(
        "backend/app/research/service.py",
        (
            "if provider is None:",
            "validate_suggestions(provider(",
            'ResearchModelError("model_provider_failed")',
            "方案生成模型尚未授权接入",
            "snapshot_json",
        ),
        "generation_failure_and_json_export_are_explicit",
    )
    text_contains(
        "backend/app/api/projects.py",
        ("/projection/retry", 'Literal["markdown", "json"]'),
        "projection_retry_and_snapshot_exports_registered",
    )
    text_contains(
        "frontend/src/pages/research/ResearchPrintPage.tsx",
        ("window.print()", "此打印件来自未保存草稿", "不可变快照"),
        "print_page_labels_saved_and_unsaved_content",
    )
    text_contains(
        "frontend/src/__tests__/research/print.test.tsx",
        (
            "saved snapshot print includes review and unknown states",
            "local draft print is visibly marked unsaved",
        ),
        "print_page_boundary_tests_available",
    )
    text_contains(
        "backend/tests/test_research_acceptance_preintegration.py",
        (
            "test_missing_plan_provider_fails_task_and_preserves_saved_content",
            "test_human_authored_plan_can_be_saved_without_generation_provider",
            "test_graph_projection_failure_preserves_snapshot_and_retry_succeeds",
            "test_constraint_change_marks_only_dependent_snapshot_for_review",
            "test_json_export_contains_frozen_versions_sources_and_review_state",
        ),
        "release_boundary_acceptance_tests_available",
    )

    failures = [check["check_id"] for check in checks if not check["passed"]]
    result = {
        "record_type": "t6-release-gate-preflight",
        "checked_at": "2026-10-04T00:00:00+08:00",
        "gate": "pass" if not failures else "fail",
        "checks": checks,
        "failed_checks": failures,
        "limitations": [
            "This is a static integration preflight, not a live API or service test.",
            "A passing preflight does not replace automated or real integration acceptance.",
        ],
    }
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
