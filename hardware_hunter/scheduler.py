from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from telegram.ext import Application

from hardware_hunter.deal_analyzer import process
from hardware_hunter.filters import accepts
from hardware_hunter.marketplaces import MercadoLivre
from hardware_hunter.notification_manager import format_offer

log = logging.getLogger(__name__)


async def publish_collected_job(context) -> None:
    db = context.application.bot_data["db"]
    for row in db.pending_collected(limit=10):
        destination = db.get_setting(int(row["added_by"]), "forward_destination")
        if not destination: continue
        title = next((line.strip() for line in row["text"].splitlines() if line.strip()), "Oferta monitorada")[:180]
        link = row["links"].splitlines()[0] if row["links"] else "Link não encontrado; verifique a mensagem original."
        price = f"R$ {row['price']:.2f}" if row["price"] is not None else "preço não identificado"
        caption = (f"🔥 Oferta monitorada\n{title}\nPreço informado: {price}\nCategoria: {row['category']}\n"
                   f"Hunter Score (relevância/completude): {row['hunter_score']}/100\nRisco: {row['risk_level']}\n"
                   f"Origem: {row['source_title']}\n{link}\n\nScore não confirma desconto de mercado; confira preço e condições.")
        try:
            media = Path(row["media_path"]) if row["media_path"] else None
            if media and media.is_file():
                await context.bot.send_photo(chat_id=int(destination), photo=media, caption=caption[:1024])
            else:
                await context.bot.send_message(chat_id=int(destination), text=caption, disable_web_page_preview=False)
            db.mark_collected_published(row["id"], datetime.now(timezone.utc).isoformat())
        except Exception:
            log.exception("Falha ao publicar mensagem coletada id=%s", row["id"])


async def monitor_job(context) -> None:
    settings = context.application.bot_data["settings"]
    db = context.application.bot_data["db"]
    if not context.application.bot_data.get("notifications_enabled", True): return
    if not settings.enable_mercado_livre:
        return
    api = MercadoLivre()
    for watch in db.watches(active_only=True):
        try:
            results = await api.search(watch["query"])
        except Exception:
            log.exception("Falha ao consultar Mercado Livre para watchlist")
            continue
        for offer in results:
            if not accepts(offer, watch["query"], watch["max_price"]): continue
            oid, score, is_new, dropped = process(db, offer, watch["max_price"])
            if score.value < watch["min_score"] or not (is_new or dropped): continue
            for user_id in settings.authorized_user_ids:
                if not db.should_notify(oid, user_id, offer.price): continue
                await context.bot.send_message(user_id, format_offer(offer, score.value, score.risk, watch["max_price"]))
                db.mark_notified(oid, user_id, offer.price, datetime.now(timezone.utc).isoformat())


def install_jobs(app: Application) -> None:
    interval = app.bot_data["settings"].poll_interval_seconds
    app.job_queue.run_repeating(monitor_job, interval=interval, first=20, name="offer-monitor")
    app.job_queue.run_repeating(publish_collected_job, interval=15, first=10, name="publish-collected")

