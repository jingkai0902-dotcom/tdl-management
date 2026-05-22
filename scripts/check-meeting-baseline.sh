#!/usr/bin/env bash
set -euo pipefail

GOLD_PATH="${GOLD_PATH:-励步英语资料库/励步5月月度会/06-会议录入人工GoldSet标注表-V1-2026-05-18.csv}"
PREDICTIONS_PATH="${PREDICTIONS_PATH:-logs/meeting-predictions-deepseek-v4-pro-2026-05-21.json}"
PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"

"$PYTHON_BIN" scripts/evaluate-meeting-goldset.py \
  --gold "$GOLD_PATH" \
  --predictions "$PREDICTIONS_PATH" \
  --fail-on-gate-violations \
  --fail-on-false-confirmed \
  --fail-on-fabricated-dates \
  --fail-on-deep-processing-errors
