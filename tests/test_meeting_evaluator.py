import json

from app.services.meeting_evaluator import (
    evaluate_meeting_classification,
    load_items,
    render_markdown_report,
)


def test_evaluate_meeting_classification_flags_false_confirmed_and_gate_violations() -> None:
    gold = load_items("励步英语资料库/励步5月月度会/06-会议录入人工GoldSet标注表-V1-2026-05-18.csv")
    predictions = [
        {
            "item_id": "F01",
            "maturity": "fact",
            "object_type": "Fact",
            "tdl_eligible": False,
            "evidence_span": "公司薪资多维表格已完成首次试运行",
        },
        {
            "item_id": "P02",
            "maturity": "confirmed",
            "object_type": "Task",
            "tdl_eligible": True,
            "evidence_span": "前端应列出哪些原始数据维度",
            "what": "列出原始数据维度",
            "who": "前端",
            "when_value": "本周五",
        },
        {
            "item_id": "I01",
            "maturity": "confirmed",
            "object_type": "Task",
            "tdl_eligible": True,
            "evidence_span": "管理者要更主动使用 AI",
            "what": "使用 AI",
            "who": "管理者",
        },
    ]

    report = evaluate_meeting_classification(gold, load_items_from_payload(predictions))

    assert report["summary"]["gold_count"] == 32
    assert report["summary"]["prediction_count"] == 3
    assert report["summary"]["matched_count"] == 3
    assert report["summary"]["false_confirmed_count"] == 2
    assert report["summary"]["fabricated_date_count"] == 1
    assert report["summary"]["deep_processing_error_count"] == 2
    assert "P02" in report["details"]["false_confirmed_ids"]
    assert "I01" in report["details"]["false_confirmed_ids"]
    assert "P02" in report["details"]["fabricated_date_ids"]
    assert any(
        violation["item_id"] == "I01"
        and violation["code"] == "confirmed_missing_3w"
        for violation in report["details"]["gate_violations"]
    )


def test_load_items_reads_json_list_and_markdown_report(tmp_path) -> None:
    predictions_path = tmp_path / "predictions.json"
    predictions_path.write_text(
        json.dumps(
            [
                {
                    "item_id": "S01",
                    "maturity": "signal",
                    "object_type": "Signal",
                    "tdl_eligible": False,
                    "evidence_span": "鑫和正在下滑、绿谷反超",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    gold = load_items("励步英语资料库/励步5月月度会/06-会议录入人工GoldSet标注表-V1-2026-05-18.csv")
    report = evaluate_meeting_classification(gold, load_items(predictions_path))
    rendered = render_markdown_report(report)

    assert report["summary"]["matched_count"] == 1
    assert report["summary"]["maturity_accuracy"] == 1.0
    assert "False confirmed count: 0" in rendered


def test_gate_violations_reject_tdl_eligible_non_task() -> None:
    report = evaluate_meeting_classification(
        [],
        load_items_from_payload(
            [
                {
                    "item_id": "bad-1",
                    "maturity": "spark",
                    "object_type": "Idea",
                    "tdl_eligible": True,
                    "evidence_span": "以后大家要多用 AI",
                }
            ]
        ),
    )

    assert report["summary"]["gate_violation_count"] == 1
    assert report["details"]["gate_violations"][0]["code"] == "invalid_tdl_eligible"


def test_gate_violations_require_evidence_support_for_tdl_eligible_items() -> None:
    report = evaluate_meeting_classification(
        [],
        load_items_from_payload(
            [
                {
                    "item_id": "tdl-1",
                    "maturity": "confirmed",
                    "object_type": "Task",
                    "tdl_eligible": True,
                    "evidence_span": "张蕾下周五前提交新师培训课表",
                    "what": "提交新师培训课表",
                    "who": "张蕾",
                    "when_value": "下周五",
                    "evidence_for_what": "提交新师培训课表",
                    "evidence_for_who": "张蕾",
                }
            ]
        ),
    )

    assert report["summary"]["gate_violation_count"] == 1
    violation = report["details"]["gate_violations"][0]
    assert violation["code"] == "tdl_missing_evidence_support"
    assert "evidence_for_when" in violation["message"]


def load_items_from_payload(rows):
    path = "/tmp/meeting-evaluator-test-predictions.json"
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(rows, handle, ensure_ascii=False)
    return load_items(path)
