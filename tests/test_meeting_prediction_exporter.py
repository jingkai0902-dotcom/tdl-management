import json

import pytest

from app.services.meeting_evaluator import load_items
from app.services.meeting_prediction_exporter import (
    ModelProviderConfig,
    build_prediction_prompt,
    item_to_jsonable,
    make_output_payload,
    prediction_from_payload,
)


def test_build_prediction_prompt_uses_gold_fragment_without_gold_answer_fields() -> None:
    prompt = build_prediction_prompt(
        {
            "item_id": "P02",
            "source_id": "meeting_2026_05_09",
            "source_type": "meeting_transcript",
            "evidence_locator": "03:49-05:24",
            "summary": "前端应列出哪些原始数据维度",
            "maturity": "pending",
            "object_type": "Issue",
            "tdl_eligible": "false",
            "notes": "有What但缺足够明确When",
        }
    )

    assert "P02" in prompt
    assert "前端应列出哪些原始数据维度" in prompt
    assert "有What但缺足够明确When" not in prompt
    assert "- maturity：pending" not in prompt
    assert "- object_type：Issue" not in prompt
    assert "- tdl_eligible：false" not in prompt
    assert "evidence_for_what、evidence_for_who、evidence_for_when" in prompt
    assert "分别摘录原片段中支撑 what、who、when_value 的文字" in prompt


def test_prediction_from_payload_accepts_fenced_json() -> None:
    item = prediction_from_payload(
        """```json
        {
          "item_id": "F01",
          "maturity": "fact",
          "object_type": "Fact",
          "tdl_eligible": false,
          "evidence_span": "公司薪资多维表格已完成首次试运行"
        }
        ```""",
        expected_item_id="F01",
    )

    assert item.item_id == "F01"
    assert item.maturity == "fact"
    assert item.object_type == "Fact"
    assert item.tdl_eligible is False


def test_prediction_from_payload_rejects_wrong_item_id() -> None:
    with pytest.raises(ValueError, match="expected 'F01'"):
        prediction_from_payload(
            json.dumps(
                {
                    "item_id": "F02",
                    "maturity": "fact",
                    "object_type": "Fact",
                    "tdl_eligible": False,
                    "evidence_span": "原始数据已能在飞书平台持续留存",
                },
                ensure_ascii=False,
            ),
            expected_item_id="F01",
        )


def test_output_payload_is_evaluator_loadable(tmp_path) -> None:
    item = prediction_from_payload(
        json.dumps(
            {
                "item_id": "S01",
                "maturity": "signal",
                "object_type": "Signal",
                "tdl_eligible": False,
                "evidence_span": "鑫和正在下滑绿谷反超",
            },
            ensure_ascii=False,
        ),
        expected_item_id="S01",
    )
    payload = make_output_payload(
        provider_config=ModelProviderConfig(
            provider="deepseek",
            model="deepseek-v4-pro",
            api_key="redacted",
            base_url="https://api.deepseek.com",
        ),
        gold_path=tmp_path / "gold.csv",
        items=[item],
    )
    output_path = tmp_path / "predictions.json"
    output_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    loaded = load_items(output_path)

    assert [item_to_jsonable(loaded_item) for loaded_item in loaded] == [
        item_to_jsonable(item)
    ]
