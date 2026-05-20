from app.roster import resolve_management_user_id, unreviewed_fuzzy_match_names


def test_fuzzy_match_review_covers_current_management_roster() -> None:
    assert unreviewed_fuzzy_match_names() == set()


def test_resolve_management_user_id_handles_known_transcription_variants() -> None:
    assert resolve_management_user_id("请李祯下周三前提交复盘") == "0611436746849471"
    assert resolve_management_user_id("请时颍下周三前提交复盘") == "0962151633-1819579479"
    assert resolve_management_user_id("不是石影的，是李珍的任务") == "0611436746849471"
    assert resolve_management_user_id("不是 Siri 的任务，是李珍的") == "0611436746849471"


def test_resolve_management_user_id_handles_english_names_and_reviewed_voice_aliases() -> None:
    assert resolve_management_user_id("请 Ellen 明天提交招聘复盘") == "2800650646785267"
    assert resolve_management_user_id("让 Hellen 明天找我") == "0611436746849471"
    assert resolve_management_user_id("请 Shery 下周提交直播复盘") == "0962151633-1819579479"
    assert resolve_management_user_id("请伞明天提交斯坦排课") == "021801686333412178"


def test_resolve_management_user_id_does_not_overmatch_voice_aliases() -> None:
    assert resolve_management_user_id("今天可能下雨要带伞") is None
    assert resolve_management_user_id("请 Siri 下周提交复盘") is None
    assert resolve_management_user_id("周日 Sunday 复盘") is None
