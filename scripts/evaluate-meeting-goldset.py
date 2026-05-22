#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.meeting_evaluator import (
    evaluate_meeting_classification,
    load_items,
    render_markdown_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate meeting classification predictions against a gold set."
    )
    parser.add_argument("--gold", required=True, help="Gold set CSV or JSON path")
    parser.add_argument(
        "--predictions",
        required=True,
        help="Prediction CSV or JSON path. Items are matched by item_id.",
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Report format. Defaults to markdown.",
    )
    parser.add_argument("--output", help="Optional report output path")
    parser.add_argument(
        "--fail-on-gate-violations",
        action="store_true",
        help="Exit with status 1 when any evaluator gate violation is present.",
    )
    parser.add_argument(
        "--fail-on-false-confirmed",
        action="store_true",
        help="Exit with status 1 when any false confirmed item is present.",
    )
    parser.add_argument(
        "--fail-on-fabricated-dates",
        action="store_true",
        help="Exit with status 1 when any fabricated date is present.",
    )
    parser.add_argument(
        "--fail-on-deep-processing-errors",
        action="store_true",
        help="Exit with status 1 when any deep processing error is present.",
    )
    args = parser.parse_args()

    report = evaluate_meeting_classification(
        load_items(args.gold),
        load_items(args.predictions),
    )
    if args.format == "json":
        rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    else:
        rendered = render_markdown_report(report)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return _exit_code_for_report(report, args)


def _exit_code_for_report(report: dict, args: argparse.Namespace) -> int:
    summary = report["summary"]
    failed = (
        (args.fail_on_gate_violations and summary["gate_violation_count"] > 0)
        or (args.fail_on_false_confirmed and summary["false_confirmed_count"] > 0)
        or (args.fail_on_fabricated_dates and summary["fabricated_date_count"] > 0)
        or (
            args.fail_on_deep_processing_errors
            and summary["deep_processing_error_count"] > 0
        )
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
