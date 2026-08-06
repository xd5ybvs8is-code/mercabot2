import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "state.db"
ENV_PATH = BASE_DIR / ".env"


@dataclass(frozen=True, slots=True)
class Settings:
    telegram_token: str
    check_interval: int
    db_path: Path
    max_concurrency: int
    request_delay: float
    tg_send_rate: int
    tg_chat_min_interval: float
    admin_user_ids: frozenset[str]
    cryptobot_api_token: str
    platega_merchant_id: str
    platega_secret: str


def _parse_check_interval(raw: str | None) -> int:
    if raw is None or raw.strip() == "":
        return 60
    interval = int(raw)
    if interval <= 0:
        raise ValueError("CHECK_INTERVAL must be a positive integer")
    return interval


def _parse_int(raw: str | None, default: int, name: str) -> int:
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _parse_float(raw: str | None, default: float, name: str) -> float:
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


def _parse_admin_ids(raw: str | None) -> frozenset[str]:
    """Parse ADMIN_USER_IDS: comma-separated Telegram user IDs.

    Игнорирует пустые и нечисловые элементы. Возвращает пустой frozenset,
    если переменная не задана или пустая (в этом случае админ-панель недоступна).
    """
    if raw is None or raw.strip() == "":
        return frozenset()
    ids: set[str] = set()
    for part in raw.split(","):
        token = part.strip()
        # Принимаем только положительные целые числа — это Telegram user_id.
        if token and token.lstrip("+").isdigit():
            ids.add(token)
    return frozenset(ids)


def load_settings(env_path: Path | None = None) -> Settings:
    load_dotenv(env_path or ENV_PATH)

    telegram_token = os.getenv("TELEGRAM_TOKEN", "").strip()

    if not telegram_token:
        raise ValueError("Missing required environment variable: TELEGRAM_TOKEN")

    # Замечание: DEVICE_UUID в .env больше не используется — у каждого
    # пользователя бота теперь свой device_uuid (см. mercari/devices.py).
    return Settings(
        telegram_token=telegram_token,
        check_interval=_parse_check_interval(os.getenv("CHECK_INTERVAL")),
        db_path=DEFAULT_DB_PATH,
        max_concurrency=_parse_int(os.getenv("MAX_CONCURRENCY"), 10, "MAX_CONCURRENCY"),
        request_delay=_parse_float(os.getenv("REQUEST_DELAY"), 0.3, "REQUEST_DELAY"),
        tg_send_rate=_parse_int(os.getenv("TG_SEND_RATE"), 20, "TG_SEND_RATE"),
        tg_chat_min_interval=_parse_float(os.getenv("TG_CHAT_MIN_INTERVAL"), 1.0, "TG_CHAT_MIN_INTERVAL"),
        admin_user_ids=_parse_admin_ids(os.getenv("ADMIN_USER_IDS")),
        cryptobot_api_token=os.getenv("CRYPTOBOT_API_TOKEN", "").strip(),
        platega_merchant_id=os.getenv("PLATEGA_MERCHANT_ID", "").strip(),
        platega_secret=os.getenv("PLATEGA_SECRET", "").strip(),
    )
