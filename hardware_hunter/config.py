from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    authorized_user_ids: frozenset[int]
    poll_interval_seconds: int
    database_path: Path
    enable_mercado_livre: bool = False
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        raw_ids = os.getenv("AUTHORIZED_USER_IDS", "")
        try:
            ids = frozenset(int(value.strip()) for value in raw_ids.split(",") if value.strip())
            interval = max(300, int(os.getenv("POLL_INTERVAL_SECONDS", "900")))
        except ValueError as exc:
            raise ValueError("AUTHORIZED_USER_IDS e POLL_INTERVAL_SECONDS devem conter números válidos") from exc
        db_path = Path(os.getenv("DATABASE_PATH", "data/hardware_hunter.sqlite3"))
        enable_ml = os.getenv("ENABLE_MERCADO_LIVRE", "false").strip().lower() in {"1", "true", "yes", "sim"}
        return cls(os.getenv("TELEGRAM_BOT_TOKEN", "").strip(), ids, interval, db_path,
                   enable_ml, os.getenv("LOG_LEVEL", "INFO").upper())

