"""Authorized Telegram MTProto collector. Run separately from the Bot API publisher."""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient, events

from hardware_hunter.config import Settings
from hardware_hunter.database import Database
from hardware_hunter.offer_pipeline import analyze_message, now_iso


async def run() -> None:
    load_dotenv()
    settings = Settings.from_env()
    try:
        api_id = int(os.environ["TELEGRAM_API_ID"])
        api_hash = os.environ["TELEGRAM_API_HASH"].strip()
    except (KeyError, ValueError) as exc:
        raise SystemExit("Configure TELEGRAM_API_ID e TELEGRAM_API_HASH no .env (my.telegram.org).") from exc
    if not api_hash: raise SystemExit("TELEGRAM_API_HASH está vazio.")
    db = Database(settings.database_path); db.initialize()
    session_path = Path(os.getenv("TELETHON_SESSION_PATH", "data/telethon.session"))
    session_path.parent.mkdir(parents=True, exist_ok=True)
    media_dir = Path("data/media"); media_dir.mkdir(parents=True, exist_ok=True)
    client = TelegramClient(str(session_path), api_id, api_hash, auto_reconnect=True, connection_retries=None)
    await client.start()
    logging.getLogger(__name__).info("Coletor conectado. Monitorando apenas grupos cadastrados no banco.")
    resolved: dict[int, dict] = {}

    async def refresh_groups():
        fresh = {}
        for row in db.monitored_groups(active_only=True):
            try:
                chat_ref = row["chat_ref"]
                lookup = int(chat_ref) if chat_ref.lstrip("-").isdigit() else chat_ref
                entity = await client.get_entity(lookup)
                marked_id = int(entity.id)
                # Telethon event.chat_id uses marked IDs for channels/supergroups.
                from telethon.utils import get_peer_id
                marked_id = get_peer_id(entity)
                fresh[marked_id] = {**row, "title": getattr(entity, "title", None) or getattr(entity, "username", None) or row["chat_ref"]}
                with db.connect() as conn:
                    conn.execute("UPDATE monitored_groups SET chat_id=?,title=? WHERE chat_ref=?", (str(marked_id), fresh[marked_id]["title"], row["chat_ref"]))
            except Exception as exc:
                logging.getLogger(__name__).warning("Grupo %s indisponível para a conta (%s)", row["chat_ref"], type(exc).__name__)
        resolved.clear(); resolved.update(fresh)

    await refresh_groups()

    async def group_refresh_loop():
        while True:
            await asyncio.sleep(60)
            await refresh_groups()

    refresh_task = asyncio.create_task(group_refresh_loop())

    @client.on(events.NewMessage)
    async def on_message(event):
        if event.out: return
        group = resolved.get(int(event.chat_id or 0))
        if group is None: return
        message = event.message
        raw_text = message.message or ""
        if not raw_text.strip(): return
        entity_links = [getattr(entity, "url", "") for entity in (message.entities or []) if getattr(entity, "url", "")]
        analysis_text = raw_text + ("\n" + "\n".join(entity_links) if entity_links else "")
        media_path = None
        if message.photo:
            try:
                media_path = await client.download_media(message, file=str(media_dir))
            except Exception as exc:
                logging.getLogger(__name__).warning("Falha ao salvar mídia de mensagem (%s)", type(exc).__name__)
        uid = int(group["added_by"])
        max_price_raw = db.get_setting(uid, "forward_max_price")
        min_score_raw = db.get_setting(uid, "hunter_min_score")
        try: max_price = float(max_price_raw) if max_price_raw else None
        except ValueError: max_price = None
        try: min_score = int(min_score_raw) if min_score_raw else 70
        except ValueError: min_score = 70
        result = analyze_message(analysis_text, bool(media_path), min_score, max_price)
        # Required keyword is a user preference; a miss moves the item to rejected, never silently approved.
        keyword = db.get_setting(uid, "forward_keyword")
        if keyword and keyword.casefold() not in raw_text.casefold():
            result["decision"] = "rejected"; result["reason"] += f"; palavra obrigatória ausente: {keyword}"
        categories_raw = db.get_setting(uid, "hunter_categories")
        if categories_raw:
            allowed_categories = {x.strip().lower() for x in categories_raw.split(",") if x.strip()}
            if result["category"] not in allowed_categories:
                result["decision"] = "rejected"; result["reason"] += "; categoria fora dos filtros"
        row = {"source_chat_id": str(event.chat_id), "source_message_id": int(message.id),
               "source_title": group["title"], "text": raw_text[:12000],
               "links": "\n".join(result["links"]), "media_path": str(media_path) if media_path else None,
               "price": result["price"], "category": result["category"], "hunter_score": result["score"],
               "risk_level": result["risk"], "decision": result["decision"], "reason": result["reason"],
               "received_at": now_iso()}
        if db.save_collected(row):
            logging.getLogger(__name__).info("Oferta %s: %s (score=%d, decision=%s)", message.id, group["title"], result["score"], result["decision"])

    while True:
        try:
            await client.run_until_disconnected()
            await asyncio.sleep(5)
            if not client.is_connected():
                await client.connect()
                await refresh_groups()
        except Exception:
            logging.getLogger(__name__).exception("Conexão MTProto interrompida; reconectando em 5s")
            await asyncio.sleep(5)
            try:
                await client.connect()
                await refresh_groups()
            except Exception:
                logging.getLogger(__name__).exception("Reconexão MTProto falhou")


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(run())


if __name__ == "__main__": main()
