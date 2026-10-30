"""Isolated layout/OCR worker: JSON on stdout, diagnostics only on stderr."""

import argparse
from contextlib import redirect_stdout
import json
import logging
import os
from pathlib import Path
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path)
    parser.add_argument(
        "--kind", choices=["paper", "report", "results", "code"], default="paper"
    )
    parser.add_argument("--no-docling", action="store_true")
    parser.add_argument("--full-formulas", action="store_true")
    parser.add_argument("--formula-input", type=Path)
    parser.add_argument("--formula-output", type=Path)
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    try:
        with redirect_stdout(sys.stderr):
            from app.knowledge.parser import parse_source, run_formula_worker

            if args.formula_input:
                if not args.formula_output:
                    raise ValueError("Formula worker requires output path")
                result = run_formula_worker(args.formula_input, args.formula_output)
            else:
                if args.input is None:
                    raise ValueError("Input file is required")
                if args.full_formulas:
                    os.environ["PAPERSTRIDE_FORMULA_MODE"] = "full"
                result = parse_source(
                    args.input, args.kind, use_docling=not args.no_docling
                )
        json.dump(result, sys.stdout, ensure_ascii=False, allow_nan=False)
        sys.stdout.write("\n")
        return 0
    except Exception as exc:
        logging.getLogger(__name__).error(
            "Source parsing failed: %s: %s", type(exc).__name__, exc
        )
        json.dump(
            {"error": str(exc), "error_type": type(exc).__name__},
            sys.stdout,
            ensure_ascii=False,
        )
        sys.stdout.write("\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
