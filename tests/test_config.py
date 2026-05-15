from app.config import load_yaml_config


def test_tdl_rules_load() -> None:
    rules = load_yaml_config("tdl_rules.yaml")

    assert rules["auto_create"]["minimum_confidence"] == 0.85
    assert rules["classification"]["minimum_confidence"] == 0.70
