#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import csv
import json
from pathlib import Path
import sys
from typing import Any

from openai import AsyncOpenAI


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.meeting_evaluator import (  # noqa: E402
    evaluate_meeting_classification,
    load_items,
    render_markdown_report,
)
from app.services.meeting_prediction_exporter import (  # noqa: E402
    make_output_payload,
    request_prediction,
    resolve_provider_config,
)


DEFAULT_GOLD = "励步英语资料库/励步5月月度会/06-会议录入人工GoldSet标注表-V1-2026-05-18.csv"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export DeepSeek/Llama meeting-classification predictions for the gold set."
    )
    parser.add_argument("--gold", default=DEFAULT_GOLD, help="Gold set CSV path")
    parser.add_argument(
        "--provider",
        choices=("deepseek", "llama"),
        required=True,
        help="OpenAI-compatible model provider to call.",
    )
    parser.add_argument("--model", help="Override model name")
    parser.add_argument("--api-key", help="Override provider API key")
    parser.add_argument("--base-url", help="Override OpenAI-compatible base URL")
    parser.add_argument(
        "--output",
        required=True,
        help="Prediction JSON output path. The JSON can be passed to evaluate-meeting-goldset.py.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Optional first-N item limit for smoke tests.",
    )
    parser.add_argument(
        "--report",
        help="Optional markdown evaluation report path generated after predictions are exported.",
    )
    parser.add_argument(
        "--fail-on-gate-violations",
        action="store_true",
        help="Exit with status 1 when evaluation finds any gate violation.",
    )
    parser.add_argument(
        "--fail-on-false-confirmed",
        action="store_true",
        help="Exit with status 1 when evaluation finds any false confirmed item.",
    )
    parser.add_argument(
        "--fail-on-fabricated-dates",
        action="store_true",
        help="Exit with status 1 when evaluation finds any fabricated date.",
    )
    parser.add_argument(
        "--fail-on-deep-processing-errors",
        action="store_true",
        help="Exit with status 1 when evaluation finds any deep processing error.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Retries per item when the provider returns an invalid or empty response.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Provider request timeout in seconds.",
    )
    args = parser.parse_args()

    return asyncio.run(_run(args))


async def _run(args: argparse.Namespace) -> int:
    gold_path = Path(args.gold)
    rows = _load_gold_rows(gold_path)
    if args.limit is not None:
        rows = rows[: args.limit]

    provider_config = resolve_provider_config(
        provider=args.provider,
        model=args.model,
        api_key=args.api_key,
        base_url=args.base_url,
    )
    client = AsyncOpenAI(
        api_key=provider_config.api_key,
        base_url=provider_config.base_url,
        timeout=args.timeout,
    )

    output_path = Path(args.output)
    predictions = _load_existing_predictions(output_path)
    predicted_ids = {item.item_id for item in predictions}
    for index, row in enumerate(rows, start=1):
        item_id = str(row.get("item_id") or "").strip()
        if item_id in predicted_ids:
            print(f"[{index}/{len(rows)}] skipping {item_id}", file=sys.stderr)
            continue
        print(f"[{index}/{len(rows)}] predicting {item_id}", file=sys.stderr)
        predictions.append(
            await _request_prediction_with_retries(
                client=client,
                model=provider_config.model,
                row=row,
                max_retries=args.max_retries,
            )
        )
        _write_predictions(
            output_path=output_path,
            provider_config=provider_config,
            gold_path=gold_path,
            predictions=predictions,
        )

    _write_predictions(
        output_path=output_path,
        provider_config=provider_config,
        gold_path=gold_path,
        predictions=predictions,
    )

    if args.report or _has_strict_eval_flags(args):
        report = evaluate_meeting_classification(
            load_items(gold_path),
            load_items(output_path),
        )
        if args.report:
            report_path = Path(args.report)
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(render_markdown_report(report), encoding="utf-8")
        if _strict_eval_failed(report, args):
            return 1
    return 0


def _has_strict_eval_flags(args: argparse.Namespace) -> bool:
    return any(
        (
            args.fail_on_gate_violations,
            args.fail_on_false_confirmed,
            args.fail_on_fabricated_dates,
            args.fail_on_deep_processing_errors,
        )
    )


def _strict_eval_failed(report: dict[str, Any], args: argparse.Namespace) -> bool:
    summary = report["summary"]
    return (
        (args.fail_on_gate_violations and summary["gate_violation_count"] > 0)
        or (args.fail_on_false_confirmed and summary["false_confirmed_count"] > 0)
        or (args.fail_on_fabricated_dates and summary["fabricated_date_count"] > 0)
        or (
            args.fail_on_deep_processing_errors
            and summary["deep_processing_error_count"] > 0
        )
    )


async def _request_prediction_with_retries(
    *,
    client: AsyncOpenAI,
    model: str,
    row: dict[str, Any],
    max_retries: int,
):
    item_id = str(row.get("item_id") or "").strip()
    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            return await request_prediction(client=client, model=model, row=row)
        except Exception as exc:
            last_error = exc
            if attempt >= max_retries:
                break
            print(
                f"  retrying {item_id} after attempt {attempt} failed: {exc}",
                file=sys.stderr,
            )
            await asyncio.sleep(min(attempt * 2, 10))
    raise RuntimeError(f"Failed to predict {item_id} after {max_retries} attempts") from last_error


def _write_predictions(
    *,
    output_path: Path,
    provider_config,
    gold_path: Path,
    predictions,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            make_output_payload(
                provider_config=provider_config,
                gold_path=gold_path,
                items=predictions,
            ),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _load_gold_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"No rows found in gold set: {path}")
    missing_ids = [index + 1 for index, row in enumerate(rows) if not row.get("item_id")]
    if missing_ids:
        raise ValueError(f"Gold set rows missing item_id: {missing_ids}")
    return rows


def _load_existing_predictions(path: Path):
    if not path.exists():
        return []
    return load_items(path)


if __name__ == "__main__":
    raise SystemExit(main())
