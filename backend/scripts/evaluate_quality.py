"""Import human-labelled JSONL and report held-out metrics; never invent labels."""

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path


def evaluate(rows):
    groups = defaultdict(list)
    seen = {}
    for row in rows:
        required = (
            "sample_key",
            "split",
            "relation_type",
            "expected",
            "predicted",
            "evidence_supported",
            "annotator",
            "source",
        )
        if any(k not in row or row[k] is None or row[k] == "" for k in required):
            raise ValueError("Each sample requires a human label, source and annotator")
        if row["split"] not in ("development", "test"):
            raise ValueError("split must be development or test")
        if any(
            type(row[k]) is not bool
            for k in ("expected", "predicted", "evidence_supported")
        ):
            raise ValueError("labels must be boolean")
        if row["sample_key"] in seen:
            raise ValueError("duplicate sample or development/test leakage")
        seen[row["sample_key"]] = row["split"]
        if row["split"] == "test":
            groups[row["relation_type"]].append(row)
    out = {}
    for relation, items in groups.items():
        tp = sum(r["predicted"] and r["expected"] for r in items)
        fp = sum(r["predicted"] and not r["expected"] for r in items)
        fn = sum(not r["predicted"] and r["expected"] for r in items)
        n = tp + fp
        precision = tp / n if n else None
        recall = tp / (tp + fn) if tp + fn else None
        if n:
            z = 1.96
            center = (precision + z * z / (2 * n)) / (1 + z * z / n)
            delta = (
                z
                * math.sqrt(precision * (1 - precision) / n + z * z / (4 * n * n))
                / (1 + z * z / n)
            )
            ci = [max(0, center - delta), min(1, center + delta)]
        else:
            ci = None
        out[relation] = {
            "samples": len(items),
            "published_samples": n,
            "precision": precision,
            "recall": recall,
            "f1": 2 * precision * recall / (precision + recall)
            if precision is not None and recall is not None and precision + recall
            else 0,
            "precision_wilson_95": ci,
            "evidence_support": sum(
                r["predicted"] and r["evidence_supported"] for r in items
            )
            / n
            if n
            else None,
            "meets_point_target": precision is not None and precision >= 0.95,
            "automatic_publication_enabled": False,
        }
    return {
        "held_out_samples": sum(len(v) for v in groups.values()),
        "by_relation": out,
        "notice": "Small samples do not establish general effectiveness. Publication remains disabled until maintainer review.",
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("labels", type=Path)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    report = evaluate(
        [
            json.loads(line)
            for line in args.labels.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    )
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
