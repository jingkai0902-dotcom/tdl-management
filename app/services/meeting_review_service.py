from __future__ import annotations

import csv
from pathlib import Path

from app.schemas import MeetingReviewItemRead, MeetingReviewRead, MeetingReviewSectionRead


GOLD_SET_PATH = (
    Path(__file__).resolve().parents[2]
    / "励步英语资料库"
    / "励步5月月度会"
    / "06-会议录入人工GoldSet标注表-V1-2026-05-18.csv"
)
GOLD_SET_SOURCE = "5月月会人工 Gold Set V1"
SECTION_ORDER = (
    ("fact", "事实"),
    ("confirmed", "已形成判断（不直接转任务）"),
    ("pending", "待处理议题"),
    ("spark", "火花 / 设想"),
    ("signal", "观察线索"),
)


def load_meeting_review() -> MeetingReviewRead:
    with GOLD_SET_PATH.open(encoding="utf-8-sig", newline="") as handle:
        items = [_item_from_row(row) for row in csv.DictReader(handle)]

    return MeetingReviewRead(
        title="励步 5 月月会判断样本",
        data_source=GOLD_SET_SOURCE,
        total_count=len(items),
        sections=[
            MeetingReviewSectionRead(
                key=key,
                title=title,
                count=sum(item.maturity == key for item in items),
                items=[item for item in items if item.maturity == key],
            )
            for key, title in SECTION_ORDER
        ],
    )


def _item_from_row(row: dict[str, str]) -> MeetingReviewItemRead:
    return MeetingReviewItemRead(
        item_id=row["item_id"],
        source_id=row["source_id"],
        source_type=row["source_type"],
        evidence_locator=row["evidence_locator"],
        summary=row["summary"],
        maturity=row["maturity"],
        object_type=row["object_type"],
        tdl_eligible=row["tdl_eligible"].lower() == "true",
        confidence=row["confidence"],
        notes=row["notes"],
    )
