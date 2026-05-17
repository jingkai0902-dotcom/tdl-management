from app.roster import resolve_management_user_id, unreviewed_fuzzy_match_names


def test_fuzzy_match_review_covers_current_management_roster() -> None:
    assert unreviewed_fuzzy_match_names() == set()


def test_resolve_management_user_id_handles_known_transcription_variants() -> None:
    assert resolve_management_user_id("请李祯下周三前提交复盘") == "0611436746849471"
    assert resolve_management_user_id("请时颍下周三前提交复盘") == "0962151633-1819579479"
