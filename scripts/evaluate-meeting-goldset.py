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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
