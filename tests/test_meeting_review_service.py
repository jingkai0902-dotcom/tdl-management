from app.services.meeting_review_service import load_meeting_review


def test_load_meeting_review_preserves_gold_set_categories_without_creating_tasks() -> None:
    review = load_meeting_review()

    assert review.total_count == 32
    assert [section.count for section in review.sections] == [8, 2, 8, 6, 8]
    assert all(not item.tdl_eligible for section in review.sections for item in section.items)
    assert review.sections[1].title == "已形成判断（不直接转任务）"
