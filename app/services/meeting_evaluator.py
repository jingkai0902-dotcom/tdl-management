from __future__ import annotations

from dataclasses import dataclass
import csv
import json
from pathlib import Path
from typing import Any


ALLOWED_MATURITIES = {"fact", "confirmed", "pending", "spark", "signal"}
ALLOWED_OBJECT_TYPES = {"Fact", "Task", "Decision", "Issue", "Idea", "Signal"}
DISALLOWED_COMBINATIONS = {
    ("spark", "Task"),
    ("signal", "Task"),
}
CONFIRMED_REQUIRED_FIELDS = ("what", "who", "when_value")
TDL_EVIDENCE_FIELDS = ("evidence_for_what", "evidence_for_who", "evidence_for_when")


@dataclass(frozen=True)
class MeetingClassificationItem:
    item_id: str
    maturity: str
    object_type: str
    tdl_eligible: bool
    evidence_span: str
    summary: str = ""
    what: str = ""
    who: str = ""
    when_value: str = ""
    evidence_for_what: str = ""
    evidence_for_who: str = ""
    evidence_for_when: str = ""


def load_items(path: str | Path) -> list[MeetingClassificationItem]:
    source_path = Path(path)
    if source_path.suffix.lower() == ".json":
        return _load_json_items(source_path)
    return _load_csv_items(source_path)


def evaluate_meeting_classification(
    gold_items: list[MeetingClassificationItem],
    predicted_items: list[MeetingClassificationItem],
) -> dict[str, Any]:
    gold_by_id = {item.item_id: item for item in gold_items}
    predicted_by_id = {item.item_id: item for item in predicted_items if item.item_id}
    matched_ids = sorted(set(gold_by_id) & set(predicted_by_id))
    missing_gold_ids = sorted(set(gold_by_id) - set(predicted_by_id))
    extra_prediction_ids = sorted(set(predicted_by_id) - set(gold_by_id))

    maturity_correct_ids = [
        item_id
        for item_id in matched_ids
        if predicted_by_id[item_id].maturity == gold_by_id[item_id].maturity
    ]
    object_type_correct_ids = [
        item_id
        for item_id in matched_ids
        if predicted_by_id[item_id].object_type == gold_by_id[item_id].object_type
    ]
    tdl_eligible_correct_ids = [
        item_id
        for item_id in matched_ids
        if predicted_by_id[item_id].tdl_eligible == gold_by_id[item_id].tdl_eligible
    ]

    predicted_confirmed_ids = [
        item.item_id for item in predicted_items if item.maturity == "confirmed"
    ]
    false_confirmed_ids = sorted(
        {
            item.item_id
            for item in predicted_items
            if item.maturity == "confirmed"
            and (
                item.item_id not in gold_by_id
                or gold_by_id[item.item_id].maturity != "confirmed"
                or _missing_task_gate_fields(item)
            )
        }
    )
    fabricated_date_ids = sorted(
        {
            item.item_id
            for item in predicted_items
            if item.when_value and (
                item.item_id not in gold_by_id
                or gold_by_id[item.item_id].maturity != "confirmed"
            )
        }
    )
    deep_processing_error_ids = sorted(
        {
            item_id
            for item_id in matched_ids
            if (
                predicted_by_id[item_id].tdl_eligible
                and not gold_by_id[item_id].tdl_eligible
            )
            or (
                predicted_by_id[item_id].object_type == "Task"
                and gold_by_id[item_id].object_type != "Task"
            )
            or (
                predicted_by_id[item_id].maturity == "confirmed"
                and gold_by_id[item_id].maturity != "confirmed"
            )
        }
    )

    gate_violations = _collect_gate_violations(predicted_items)

    return {
        "summary": {
            "gold_count": len(gold_items),
            "prediction_count": len(predicted_items),
            "matched_count": len(matched_ids),
            "missing_gold_count": len(missing_gold_ids),
            "extra_prediction_count": len(extra_prediction_ids),
            "maturity_accuracy": _ratio(len(maturity_correct_ids), len(matched_ids)),
            "object_type_accuracy": _ratio(len(object_type_correct_ids), len(matched_ids)),
            "tdl_eligible_accuracy": _ratio(
                len(tdl_eligible_correct_ids), len(matched_ids)
            ),
            "predicted_confirmed_count": len(predicted_confirmed_ids),
            "false_confirmed_count": len(false_confirmed_ids),
            "false_confirmed_rate": _ratio(
                len(false_confirmed_ids), len(predicted_confirmed_ids)
            ),
            "fabricated_date_count": len(fabricated_date_ids),
            "deep_processing_error_count": len(deep_processing_error_ids),
            "gate_violation_count": len(gate_violations),
        },
        "details": {
            "missing_gold_ids": missing_gold_ids,
            "extra_prediction_ids": extra_prediction_ids,
            "maturity_mismatch_ids": [
                item_id for item_id in matched_ids if item_id not in maturity_correct_ids
            ],
            "object_type_mismatch_ids": [
                item_id
                for item_id in matched_ids
                if item_id not in object_type_correct_ids
            ],
            "tdl_eligible_mismatch_ids": [
                item_id
                for item_id in matched_ids
                if item_id not in tdl_eligible_correct_ids
            ],
            "false_confirmed_ids": false_confirmed_ids,
            "fabricated_date_ids": fabricated_date_ids,
            "deep_processing_error_ids": deep_processing_error_ids,
            "gate_violations": gate_violations,
        },
    }


def render_markdown_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    details = report["details"]
    lines = [
        "# Meeting Classification Evaluation",
        "",
        "## Summary",
        "",
        f"- Gold items: {summary['gold_count']}",
        f"- Predicted items: {summary['prediction_count']}",
        f"- Matched items: {summary['matched_count']}",
        f"- Maturity accuracy: {_format_ratio(summary['maturity_accuracy'])}",
        f"- Object type accuracy: {_format_ratio(summary['object_type_accuracy'])}",
        f"- TDL eligibility accuracy: {_format_ratio(summary['tdl_eligible_accuracy'])}",
        f"- False confirmed rate: {_format_ratio(summary['false_confirmed_rate'])}",
        f"- False confirmed count: {summary['false_confirmed_count']}",
        f"- Fabricated date count: {summary['fabricated_date_count']}",
        f"- Deep processing error count: {summary['deep_processing_error_count']}",
        f"- Gate violation count: {summary['gate_violation_count']}",
        "",
        "## Details",
        "",
        _format_id_line("Missing gold ids", details["missing_gold_ids"]),
        _format_id_line("Extra prediction ids", details["extra_prediction_ids"]),
        _format_id_line("Maturity mismatches", details["maturity_mismatch_ids"]),
        _format_id_line("Object type mismatches", details["object_type_mismatch_ids"]),
        _format_id_line("TDL eligibility mismatches", details["tdl_eligible_mismatch_ids"]),
        _format_id_line("False confirmed ids", details["false_confirmed_ids"]),
        _format_id_line("Fabricated date ids", details["fabricated_date_ids"]),
        _format_id_line("Deep processing error ids", details["deep_processing_error_ids"]),
    ]
    if details["gate_violations"]:
        lines.extend(["", "## Gate Violations", ""])
        for violation in details["gate_violations"]:
            lines.append(
                f"- {violation['item_id']}: {violation['code']} - {violation['message']}"
            )
    return "\n".join(lines) + "\n"


def _load_csv_items(path: Path) -> list[MeetingClassificationItem]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [_item_from_mapping(row) for row in csv.DictReader(handle)]


def _load_json_items(path: Path) -> list[MeetingClassificationItem]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload["items"] if isinstance(payload, dict) and "items" in payload else payload
    if not isinstance(rows, list):
        raise ValueError("JSON predictions must be a list or an object with an 'items' list")
    return [_item_from_mapping(row) for row in rows]


def _item_from_mapping(row: dict[str, Any]) -> MeetingClassificationItem:
    return MeetingClassificationItem(
        item_id=str(row.get("item_id") or "").strip(),
        maturity=str(row.get("maturity") or "").strip(),
        object_type=str(row.get("object_type") or "").strip(),
        tdl_eligible=_parse_bool(row.get("tdl_eligible")),
        evidence_span=str(row.get("evidence_span") or row.get("summary") or "").strip(),
        summary=str(row.get("summary") or "").strip(),
        what=str(row.get("what") or "").strip(),
        who=str(row.get("who") or "").strip(),
        when_value=str(row.get("when_value") or "").strip(),
        evidence_for_what=str(row.get("evidence_for_what") or "").strip(),
        evidence_for_who=str(row.get("evidence_for_who") or "").strip(),
        evidence_for_when=str(row.get("evidence_for_when") or "").strip(),
    )


def _collect_gate_violations(items: list[MeetingClassificationItem]) -> list[dict[str, str]]:
    violations: list[dict[str, str]] = []
    for item in items:
        if item.maturity not in ALLOWED_MATURITIES:
            violations.append(
                _violation(item, "invalid_maturity", f"Unknown maturity '{item.maturity}'")
            )
        if item.object_type not in ALLOWED_OBJECT_TYPES:
            violations.append(
                _violation(
                    item,
                    "invalid_object_type",
                    f"Unknown object_type '{item.object_type}'",
                )
            )
        if (item.maturity, item.object_type) in DISALLOWED_COMBINATIONS:
            violations.append(
                _violation(
                    item,
                    "disallowed_combination",
                    f"{item.maturity}+{item.object_type} is not allowed",
                )
            )
        if item.maturity == "confirmed" and _requires_task_gate(item):
            missing = _missing_task_gate_fields(item)
            if missing:
                violations.append(
                    _violation(
                        item,
                        "confirmed_missing_3w",
                        f"confirmed item missing {', '.join(missing)}",
                    )
                )
            if not item.evidence_span:
                violations.append(
                    _violation(item, "confirmed_missing_evidence", "confirmed item missing evidence_span")
                )
        if item.tdl_eligible and not (
            item.maturity == "confirmed" and item.object_type == "Task"
        ):
            violations.append(
                _violation(
                    item,
                    "invalid_tdl_eligible",
                    "tdl_eligible=true requires confirmed+Task",
                )
            )
        if item.tdl_eligible and item.maturity == "confirmed" and item.object_type == "Task":
            missing_evidence = _missing_tdl_evidence_fields(item)
            if missing_evidence:
                violations.append(
                    _violation(
                        item,
                        "tdl_missing_evidence_support",
                        f"tdl_eligible item missing {', '.join(missing_evidence)}",
                    )
                )
    return violations


def _requires_task_gate(item: MeetingClassificationItem) -> bool:
    return item.object_type == "Task" or item.tdl_eligible


def _missing_task_gate_fields(item: MeetingClassificationItem) -> list[str]:
    if not _requires_task_gate(item):
        return []
    return [
        field_name
        for field_name in CONFIRMED_REQUIRED_FIELDS
        if not getattr(item, field_name)
    ]


def _missing_tdl_evidence_fields(item: MeetingClassificationItem) -> list[str]:
    if not item.tdl_eligible:
        return []
    return [field_name for field_name in TDL_EVIDENCE_FIELDS if not getattr(item, field_name)]


def _violation(item: MeetingClassificationItem, code: str, message: str) -> dict[str, str]:
    return {"item_id": item.item_id or "-", "code": code, "message": message}


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _format_ratio(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.1%}"


def _format_id_line(label: str, ids: list[str]) -> str:
    return f"- {label}: {', '.join(ids) if ids else 'none'}"
