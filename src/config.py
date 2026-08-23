import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent.parent
SWING_SCREENING_CONFIG_PATH = ROOT_DIR / "config" / "swing_screening.yaml"


class Settings:
    jquants_api_key = os.getenv("JQUANTS_API_KEY")

    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")


settings = Settings()


def load_swing_config() -> dict:
    with open(SWING_SCREENING_CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)
