from app.config import load_yaml_config


def test_tdl_rules_load() -> None:
    rules = load_yaml_config("tdl_rules.yaml")

    assert rules["auto_create"]["minimum_confidence"] == 0.85
    assert rules["classification"]["minimum_confidence"] == 0.70


def test_management_roster_includes_known_shift_types() -> None:
    roster = load_yaml_config("management_roster.yaml")
    by_name = {item["name"]: item for item in roster["management"]}

    assert by_name["张皓"]["shift_type"] == "standard_shift"
    assert by_name["时颖"]["shift_type"] == "operations_shift"
    assert by_name["赵晓华"]["shift_type"] == "teacher_shift"
    assert by_name["李珍"]["shift_type"] is None
    assert by_name["张蕾"]["shift_type"] is None
