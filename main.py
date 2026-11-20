"""Hardware Hunter BR entry point."""
from __future__ import annotations

import logging

from hardware_hunter.bot import build_application
from hardware_hunter.config import Settings
from hardware_hunter.database import Database


def main() -> None:
    settings = Settings.from_env()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if not settings.telegram_bot_token:
        raise SystemExit("TELEGRAM_BOT_TOKEN ausente. Configure o arquivo .env.")
    if not settings.authorized_user_ids:
        raise SystemExit("AUTHORIZED_USER_IDS ausente. Configure ao menos seu ID numérico do Telegram.")
    database = Database(settings.database_path)
    database.initialize()
    app = build_application(settings, database)
    logging.getLogger(__name__).info("Hardware Hunter BR iniciado")
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
