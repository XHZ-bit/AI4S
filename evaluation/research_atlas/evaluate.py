"""Deterministic scorer for Research Atlas human-reviewed evaluation JSONL.

This script never calls a model or reads paper files. Incomplete annotations are
reported but excluded from all effectiveness metric denominators.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


PARTITIONS = {"development", "same_domain_holdout", "cross_domain", "synthetic"}
FINDING_STATUSES = {"unknown", "not_found", "not_parsed", "conflicting", "reported"}
CONDITION_RESULTS = {"compatible", "incompatible", "insufficient"}
PLAN_SECTIONS = {"objective", "route", "data_and_split", "metrics", "steps", "risks"}


class EvaluationInputError(ValueError):
    """Raised when a record cannot be scored without silently guessing."""


def _ratio(numerator: int | float, denominator: int | float) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def _require(record: dict[str, Any], key: str, expected_type: type) -> Any:
    if key not in record:
        raise EvaluationInputError(f"missing required field: {key}")
    value = record[key]
    if not isinstance(value, expected_type):
        raise EvaluationInputError(f"{key} must be {expected_type.__name__}")
    return value


def _validate_field(field: dict[str, Any], record_id: str) -> None:
    for key in ("field_id", "kind", "finding_status", "evidence"):
        if key not in field:
            raise EvaluationInputError(f"{record_id}: field missing {key}")
    if field["finding_status"] not in FINDING_STATUSES:
        raise EvaluationInputError(f"{record_id}: invalid finding_status")
    if not isinstance(field["evidence"], dict):
        raise EvaluationInputError(f"{record_id}: evidence must be an object")


def validate_record(record: dict[str, Any]) -> None:
    record_id = _require(record, "record_id", str)
    if record.get("partition") not in PARTITIONS:
        raise EvaluationInputError(f"{record_id}: invalid partition")
    if record.get("annotation_status") not in {"incomplete", "completed"}:
        raise EvaluationInputError(f"{record_id}: invalid annotation_status")
    annotator = _require(record, "annotator", dict)
    if record["annotation_status"] == "completed" and not annotator.get(
        "human_reviewed"
    ):
        raise EvaluationInputError(
            f"{record_id}: completed annotations require human_reviewed=true"
        )
    gold = _require(record, "gold_fields", list)
    predicted = _require(record, "predicted_fields", list)
    for field in [*gold, *predicted]:
        if not isinstance(field, dict):
            raise EvaluationInputError(f"{record_id}: fields must be objects")
        _validate_field(field, record_id)
    for key in ("manual_actions", "plan_sections", "time_minutes", "contamination"):
        _require(record, key, dict)
    for check in _require(record, "condition_checks", list):
        if check.get("expected") not in CONDITION_RESULTS:
            raise EvaluationInputError(f"{record_id}: invalid expected condition")
        if check.get("actual") not in CONDITION_RESULTS:
            raise EvaluationInputError(f"{record_id}: invalid actual condition")
    for check in _require(record, "citation_checks", list):
        if not isinstance(check.get("located"), bool):
            raise EvaluationInputError(f"{record_id}: located must be boolean")
    missing_sections = PLAN_SECTIONS - set(record["plan_sections"])
    if missing_sections:
        raise EvaluationInputError(
            f"{record_id}: missing plan sections {sorted(missing_sections)}"
        )


def _field_signature(field: dict[str, Any]) -> str:
    comparable = {
        "field_id": field["field_id"],
        "kind": field["kind"],
        "value": field.get("value"),
        "finding_status": field["finding_status"],
        "evidence": field["evidence"],
    }
    return json.dumps(comparable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def evaluate(records: list[dict[str, Any]]) -> dict[str, Any]:
    for record in records:
        validate_record(record)

    completed = [r for r in records if r["annotation_status"] == "completed"]
    incomplete = [r for r in records if r["annotation_status"] == "incomplete"]
    tp = fp = fn = 0
    manual_actions = 0
    final_fields = 0
    condition_correct = condition_total = 0
    citations_located = citations_total = 0
    plan_present = plan_total = 0
    time_totals = {"preparation": 0.0, "review": 0.0, "correction": 0.0}

    for record in completed:
        gold = {_field_signature(field) for field in record["gold_fields"]}
        predicted = {_field_signature(field) for field in record["predicted_fields"]}
        tp += len(gold & predicted)
        fp += len(predicted - gold)
        fn += len(gold - predicted)
        actions = record["manual_actions"]
        manual_actions += sum(int(actions.get(key, 0)) for key in ("added", "corrected", "removed"))
        final_fields += len(record["gold_fields"])
        for check in record["condition_checks"]:
            condition_total += 1
            condition_correct += int(check["expected"] == check["actual"])
        for check in record["citation_checks"]:
            citations_total += 1
            citations_located += int(check["located"])
        for section in PLAN_SECTIONS:
            plan_total += 1
            plan_present += int(bool(record["plan_sections"][section]))
        for key in time_totals:
            time_totals[key] += float(record["time_minutes"].get(key, 0))

    contaminated = [
        r["record_id"]
        for r in records
        if r["contamination"].get("used_by_development")
    ]
    return {
        "evaluation_format": "research-atlas-evaluation-v1",
        "record_counts": {
            "total": len(records),
            "completed": len(completed),
            "incomplete_excluded": len(incomplete),
            "by_partition": {
                partition: sum(r["partition"] == partition for r in records)
                for partition in sorted(PARTITIONS)
            },
        },
        "automatic_extraction": {
            "exact_true_positive": tp,
            "false_positive_or_mismatch": fp,
            "omitted_or_mismatch": fn,
            "precision": _ratio(tp, tp + fp),
            "recall": _ratio(tp, tp + fn),
            "f1": _ratio(2 * tp, 2 * tp + fp + fn),
        },
        "human_intervention": {
            "actions": manual_actions,
            "final_gold_fields": final_fields,
            "actions_per_final_field": _ratio(manual_actions, final_fields),
        },
        "condition_check_accuracy": _ratio(condition_correct, condition_total),
        "citation_location_success_rate": _ratio(citations_located, citations_total),
        "plan_structure_completeness": _ratio(plan_present, plan_total),
        "time_minutes": {
            **{key: round(value, 3) for key, value in time_totals.items()},
            "total": round(sum(time_totals.values()), 3),
        },
        "contamination": {
            "independent_holdout_valid": not contaminated,
            "contaminated_record_ids": contaminated,
        },
        "interpretation_limits": [
            "Incomplete annotations are excluded from all metric denominators.",
            "Exact field matching includes value, missing status, and evidence locator.",
            "Synthetic inputs validate the scorer only and are not real-paper effectiveness evidence.",
        ],
    }


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EvaluationInputError(f"line {line_number}: invalid JSON") from exc
        if not isinstance(value, dict):
            raise EvaluationInputError(f"line {line_number}: record must be an object")
        records.append(value)
    return records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate(load_jsonl(args.input))
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

