"""Create blank validation packs, not fabricated expert labels or trial outcomes."""

import argparse
import csv
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    samples = args.output / "quality-labels.jsonl"
    if samples.exists():
        raise SystemExit("Refusing to overwrite existing annotation work")
    categories = [
        "direct_support",
        "negation",
        "conditions",
        "homonym",
        "unsupported",
        "table_context",
    ]
    with samples.open("w", encoding="utf-8") as handle:
        for i in range(200):
            handle.write(
                json.dumps(
                    {
                        "sample_key": f"sample-{i + 1:03}",
                        "split": "development" if i < 50 else "test",
                        "category": categories[i % len(categories)],
                        "relation_type": None,
                        "expected": None,
                        "predicted": None,
                        "evidence_supported": None,
                        "annotator": None,
                        "source": None,
                        "notes": "",
                    }
                )
                + "\n"
            )
    with (args.output / "user-trials.csv").open(
        "x", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "participant_id",
                "order",
                "condition",
                "task_kind",
                "task_id",
                "minutes",
                "success",
                "rubric_score",
                "help_count",
                "abandoned",
                "rater",
                "notes",
            ]
        )
        for i in range(1, 9):
            order = ["baseline", "atlas"] if i % 2 else ["atlas", "baseline"]
            for n, condition in enumerate(order, 1):
                for kind in ("reading", "reproduction", "research"):
                    writer.writerow(
                        [f"P{i:02}", n, condition, kind, "", "", "", "", "", "", "", ""]
                    )
    (args.output / "seed-review.json").write_text(
        json.dumps(
            {
                "topic": "Diffusion Policy",
                "status": "awaiting_human_review",
                "papers": [
                    {
                        "slot": i + 1,
                        "paper_uid": None,
                        "source": None,
                        "reviewer": None,
                        "reviewed_at": None,
                        "notes": "",
                    }
                    for i in range(20)
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        "Created 200 unlabelled samples, 8 counterbalanced trial forms and 20 seed review slots."
    )


if __name__ == "__main__":
    main()
