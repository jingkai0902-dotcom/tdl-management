from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    app_env: str = "development"
    app_name: str = "tdl-backend"
    database_url: str = "postgresql+asyncpg://tdl:tdl@127.0.0.1:5432/tdl"

    openai_api_key: str = ""
    openai_model: str = "gpt-5.5"
    openai_base_url: str = ""
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-v4-pro"

    dingtalk_app_key: str = ""
    dingtalk_app_secret: str = ""
    dingtalk_agent_id: str = ""
    dingtalk_tdl_card_template_id: str = ""
    dingtalk_require_interactive_reminder_cards: bool = False
    dingtalk_oauth_scope: str = "openid Contact.User.Read Calendar.Event.Read Calendar.Event.Write"
    dingtalk_oauth_redirect_uri: str = ""
    dingtalk_async_intake_enabled: bool = False
    public_base_url: str = ""
    scheduler_timezone: str = "Asia/Shanghai"
    workbench_v0_enabled: bool = False
    runtime_state_dir: str = ""
    internal_api_key: str = ""

    feishu_app_id: str = ""
    feishu_app_secret: str = ""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def load_yaml_config(name: str) -> dict[str, Any]:
    path = BASE_DIR / "config" / name
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}
