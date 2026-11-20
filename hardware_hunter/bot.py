from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters)
import httpx

from hardware_hunter.config import Settings
from hardware_hunter.database import Database
from hardware_hunter.deal_analyzer import process
from hardware_hunter.filters import accepts
from hardware_hunter.marketplaces import MercadoLivre
from hardware_hunter.models import Offer
from hardware_hunter.notification_manager import format_offer
from hardware_hunter.price_history import summarize
from hardware_hunter.scheduler import install_jobs

log = logging.getLogger(__name__)


def authorized(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    settings: Settings = context.application.bot_data["settings"]
    user = update.effective_user
    return bool(user and user.id in settings.authorized_user_ids)


async def guard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not authorized(update, context):
        if update.effective_message:
            await update.effective_message.reply_text("Este bot é privado e seu usuário não está autorizado.")
        return False
    return True


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update, context): return
    await update.effective_message.reply_text("Hardware Hunter BR ativo. Use /help para ver os comandos.\n\nA busca automática monitora sua watchlist pelo Mercado Livre.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update, context): return
    await update.effective_message.reply_text(
        "Comandos disponíveis:\n"
        "/pesquisar <produto> — buscar agora\n/adicionar <produto> [preço máximo] — incluir na watchlist\n"
        "/remover <produto> — remover\n/watchlist — listar monitoramento\n/ofertas — ranking observado\n"
        "/achadinhos — ofertas com score 80+\n/gpu, /cpu, /ram, /ssd, /fontes, /mouse, /monitor — buscar categoria\n"
        "/kits — buscar kits; /revenda — status da estimativa\n/historico <termo> — resumo da amostra observada\n"
        "/precos <termo> — comparação de ofertas observadas\n/ranking — ranking; /favoritos — favoritos\n"
        "/config — configurações; /status — estado; /pausar e /retomar — alertas\n/resumo — resumo de ofertas; /limpar — pedir confirmação para limpar ofertas."
        "\n/filtro — configurar limite de preço e palavra obrigatória; /origem — registrar grupo monitorado; /destino — definir o grupo de publicação."
    )


async def add_watch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update, context): return
    args = context.args
    if not args:
        await update.effective_message.reply_text("Uso: /adicionar RTX 3060 [1000]"); return
    price = None
    if args[-1].replace(",", ".").replace(".", "", 1).isdigit():
        price = float(args.pop().replace(",", "."))
    query = " ".join(args).strip()
    if not query:
        await update.effective_message.reply_text("Informe o nome do produto."); return
    created = context.application.bot_data["db"].add_watch(query, max_price=price)
    await update.effective_message.reply_text(("Adicionado" if created else "Já estava na watchlist") + (f": {query}" + (f" (máximo R$ {price:.2f})" if price else "")))


async def remove_watch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update, context): return
    query = " ".join(context.args).strip()
    if not query:
        await update.effective_message.reply_text("Uso: /remover <produto>"); return
    ok = context.application.bot_data["db"].remove_watch(query)
    await update.effective_message.reply_text("Removido." if ok else "Produto não encontrado na watchlist.")


async def watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update, context): return
    rows = context.application.bot_data["db"].watches()
    if not rows: text = "Watchlist vazia. Adicione com /adicionar <produto>."
    else: text = "Watchlist:\n" + "\n".join(f"• {r['query']}" + (f" — até R$ {r['max_price']:.2f}" if r["max_price"] else "") + (" (pausado)" if not r["active"] else "") for r in rows)
    await update.effective_message.reply_text(text)


async def search(update: Update, context: ContextTypes.DEFAULT_TYPE, forced: str | None = None) -> None:
    if not await guard(update, context): return
    query = forced or " ".join(context.args).strip()
    if not query:
        await update.effective_message.reply_text("Informe o produto. Exemplo: /pesquisar RTX 3060"); return
    if not context.application.bot_data["settings"].enable_mercado_livre:
        await update.effective_message.reply_text("A busca no Mercado Livre está desativada. Amazon, Shopee e OLX ainda não têm integração autorizada ativa neste projeto."); return
    await update.effective_message.reply_text(f"Pesquisando “{query}” no Mercado Livre…")
    try:
        offers = await MercadoLivre().search(query, limit=20)
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        log.exception("Mercado Livre respondeu HTTP %s", status_code)
        if status_code in (401, 403):
            detail = f"O Mercado Livre recusou a consulta (HTTP {status_code}). Pode exigir credencial ou permissão da API."
        elif status_code == 429:
            detail = "O Mercado Livre limitou temporariamente as consultas (HTTP 429). Aguarde alguns minutos e tente novamente."
        else:
            detail = f"O Mercado Livre respondeu com erro HTTP {status_code}."
        await update.effective_message.reply_text(detail + " Veja o terminal do bot para o registro técnico."); return
    except httpx.RequestError as exc:
        log.exception("Falha de conexão durante busca no Mercado Livre (%s)", type(exc).__name__)
        await update.effective_message.reply_text("Não consegui conectar à API do Mercado Livre. Confira a internet e tente novamente; veja o terminal para o erro técnico."); return
    except Exception:
        log.exception("Erro inesperado durante busca no Mercado Livre")
        await update.effective_message.reply_text("A busca falhou por um erro inesperado. Veja o terminal do bot para o registro técnico."); return
    db = context.application.bot_data["db"]
    db.log_search(query, len(offers))
    matched = [o for o in offers if accepts(o, query)]
    if not matched:
        await update.effective_message.reply_text(f"Nenhum resultado correspondente para {query}."); return
    for offer in matched[:8]:
        oid, score, _, _ = process(db, offer)
        buttons = [[InlineKeyboardButton("Abrir oferta", url=offer.url),
                    InlineKeyboardButton("⭐ Favoritar", callback_data=f"fav:{oid}"),
                    InlineKeyboardButton("Ignorar", callback_data=f"ignore:{oid}")]]
        await update.effective_message.reply_text(format_offer(offer, score.value, score.risk),
                                                  reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await search(update, context)


def category_search(term: str):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await search(update, context, " ".join(context.args) or term)
    return handler


async def listings(update: Update, context: ContextTypes.DEFAULT_TYPE, minimum: int = 0) -> None:
    if not await guard(update, context): return
    rows = context.application.bot_data["db"].offers(minimum, 10)
    if not rows:
        await update.effective_message.reply_text("Ainda não há ofertas registradas. Use /pesquisar ou adicione itens à watchlist."); return
    label = "Ranking observado" if minimum == 0 else "Achadinhos (score 80+)"
    text = label + ":\n\n" + "\n\n".join(f"{i+1}. {r['title']} — R$ {r['price']:.2f}\nScore {r['hunter_score']}/100 · risco {r['risk_level']}\n{r['url']}" for i, r in enumerate(rows))
    await update.effective_message.reply_text(text, disable_web_page_preview=True)


async def offers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None: await listings(update, context)
async def bargains(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None: await listings(update, context, 80)


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update, context): return
    query = " ".join(context.args).strip()
    if not query: await update.effective_message.reply_text("Uso: /historico <termo>"); return
    stats = summarize(context.application.bot_data["db"], query)
    if not stats: await update.effective_message.reply_text("Sem preços observados para esse termo."); return
    await update.effective_message.reply_text(f"Amostra atual de anúncios que correspondem a “{query}” (não representa série histórica completa):\nQuantidade: {stats['count']}\nMínimo: R$ {stats['min']:.2f}\nMediana: R$ {stats['median']:.2f}\nMédia: R$ {stats['mean']:.2f}\nMáximo: R$ {stats['max']:.2f}")


async def favorite_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update, context): return
    rows = context.application.bot_data["db"].favorites(update.effective_user.id)
    await update.effective_message.reply_text("Favoritos:\n" + "\n".join(f"• {r['title']} — R$ {r['price']:.2f}\n{r['url']}" for r in rows) if rows else "Você ainda não tem favoritos.", disable_web_page_preview=True)


async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if update.effective_user.id not in context.application.bot_data["settings"].authorized_user_ids:
        await q.answer("Não autorizado", show_alert=True); return
    action, raw_id = q.data.split(":", 1)
    if action == "fav":
        state = context.application.bot_data["db"].toggle_favorite(update.effective_user.id, int(raw_id))
        await q.answer("Adicionado aos favoritos" if state else "Removido dos favoritos")
    else:
        await q.answer("Oferta ignorada nesta conversa")
        await q.edit_message_reply_markup(reply_markup=None)


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update, context): return
    app = context.application
    settings = app.bot_data["settings"]
    await update.effective_message.reply_text(f"Bot ativo. Alertas: {'ativos' if app.bot_data.get('notifications_enabled', True) else 'pausados'}.\nWatchlist: {len(app.bot_data['db'].watches())}.\nIntervalo: {settings.poll_interval_seconds}s.\nMercado Livre: {'habilitado' if settings.enable_mercado_livre else 'desativado'}. Amazon/Shopee/OLX: sem integração ativa; não há ofertas automáticas dessas fontes.")


async def config(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update, context): return
    await status(update, context)


async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update, context): return
    context.application.bot_data["notifications_enabled"] = False
    await update.effective_message.reply_text("Alertas pausados. Buscas manuais continuam disponíveis.")


async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update, context): return
    context.application.bot_data["notifications_enabled"] = True
    await update.effective_message.reply_text("Alertas retomados.")


async def clear_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update, context): return
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Confirmar limpeza", callback_data="clear:yes"), InlineKeyboardButton("Cancelar", callback_data="clear:no")]])
    await update.effective_message.reply_text("Remover ofertas e histórico associados? Essa ação não pode ser desfeita.", reply_markup=kb)


async def clear_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if update.effective_user.id not in context.application.bot_data["settings"].authorized_user_ids:
        await q.answer("Não autorizado", show_alert=True); return
    if q.data == "clear:yes":
        context.application.bot_data["db"].clear_offers()
        await q.edit_message_text("Ofertas, histórico, favoritos e notificações foram removidos.")
    else: await q.edit_message_text("Limpeza cancelada.")
    await q.answer()


async def misc_command(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    if not await guard(update, context): return
    await update.effective_message.reply_text(text)


def parse_price(text: str) -> float | None:
    match = re.search(r"R\$\s*([0-9]{1,3}(?:\.[0-9]{3})*(?:,[0-9]{1,2})?|[0-9]+(?:,[0-9]{1,2})?)", text, re.I)
    if not match: return None
    try: return float(match.group(1).replace(".", "").replace(",", "."))
    except ValueError: return None


def extract_link(message) -> str | None:
    entities = list(message.entities or []) + list(message.caption_entities or [])
    for entity in entities:
        if entity.type == "text_link" and entity.url: return entity.url
        if entity.type == "url":
            text = message.text or message.caption or ""
            return text[entity.offset:entity.offset + entity.length]
    match = re.search(r"https?://\S+", message.text or message.caption or "", re.I)
    return match.group(0).rstrip(".,)") if match else None


async def filter_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update, context): return
    db, uid = context.application.bot_data["db"], update.effective_user.id
    args = context.args
    if not args:
        maximum = db.get_setting(uid, "forward_max_price")
        keyword = db.get_setting(uid, "forward_keyword")
        await update.effective_message.reply_text(f"Filtros de encaminhamentos:\nPreço máximo: {('R$ ' + maximum) if maximum else 'sem limite'}\nPalavra obrigatória: {keyword or 'nenhuma'}\n\nUse /filtro max 1200, /filtro palavra RTX ou /filtro limpar.")
        return
    action = args[0].lower()
    if action == "limpar":
        db.set_setting(uid, "forward_max_price", "")
        db.set_setting(uid, "forward_keyword", "")
        await update.effective_message.reply_text("Filtros de encaminhamento limpos."); return
    if action == "max" and len(args) > 1:
        try: value = float(args[1].replace("R$", "").replace(".", "").replace(",", "."))
        except ValueError:
            await update.effective_message.reply_text("Preço inválido. Exemplo: /filtro max 1200 ou /filtro max 1.200,50"); return
        if value <= 0:
            await update.effective_message.reply_text("Informe um preço acima de zero."); return
        db.set_setting(uid, "forward_max_price", str(value))
        await update.effective_message.reply_text(f"Preço máximo definido: R$ {value:.2f}."); return
    if action == "palavra" and len(args) > 1:
        value = " ".join(args[1:]).strip()
        db.set_setting(uid, "forward_keyword", value)
        await update.effective_message.reply_text(f"Só vou aprovar encaminhamentos contendo: {value}"); return
    await update.effective_message.reply_text("Uso: /filtro max 1200 | /filtro palavra RTX | /filtro limpar")


async def set_destination(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update, context): return
    if update.effective_chat.type == "private":
        await update.effective_message.reply_text("Adicione o bot ao seu grupo, torne-o administrador com permissão para publicar e envie /destino dentro do grupo."); return
    context.application.bot_data["db"].set_setting(update.effective_user.id, "forward_destination", str(update.effective_chat.id))
    await update.effective_message.reply_text("Este grupo foi definido como destino das ofertas aprovadas para sua conta.")


async def set_source(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update, context): return
    if update.effective_chat.type == "private":
        await update.effective_message.reply_text("Adicione o bot ao grupo de origem e envie /origem dentro dele. Para remover, use /origem remover."); return
    db, uid, chat_id = context.application.bot_data["db"], update.effective_user.id, update.effective_chat.id
    if context.args and context.args[0].lower() == "remover":
        removed = db.remove_source_group(uid, chat_id)
        await update.effective_message.reply_text("Este grupo não será mais monitorado." if removed else "Este grupo não estava registrado para sua conta.")
        return
    db.add_source_group(uid, chat_id)
    await update.effective_message.reply_text("Grupo registrado como origem. Vou analisar novas mensagens com preço explícito no formato R$ ... e aplicar seus filtros.")


async def forwarded_offer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update, context): return
    await process_candidate(update.effective_message, update.effective_user.id, context, reply_to_user=True)


async def source_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg or not update.effective_user or update.effective_user.is_bot: return
    owner = context.application.bot_data["db"].source_owner(msg.chat_id)
    if owner is None: return
    await process_candidate(msg, owner, context, reply_to_user=False)


async def process_candidate(msg, uid: int, context: ContextTypes.DEFAULT_TYPE, reply_to_user: bool) -> None:
    body = msg.text or msg.caption or ""
    price = parse_price(body)
    link = extract_link(msg)
    if price is None:
        if reply_to_user: await msg.reply_text("Não encontrei um preço no formato R$ 1.234,56. Encaminhe uma oferta com o preço visível.")
        return
    db = context.application.bot_data["db"]
    maximum = db.get_setting(uid, "forward_max_price")
    keyword = db.get_setting(uid, "forward_keyword")
    if maximum and price > float(maximum):
        if reply_to_user: await msg.reply_text(f"Oferta filtrada: R$ {price:.2f} supera seu limite de R$ {float(maximum):.2f}.")
        return
    if keyword and keyword.casefold() not in body.casefold():
        if reply_to_user: await msg.reply_text(f"Oferta filtrada: não encontrei a palavra obrigatória “{keyword}”.")
        return
    title = next((line.strip() for line in body.splitlines() if line.strip() and not line.strip().startswith("http")), "Oferta encaminhada")[:180]
    summary = f"✅ Oferta aprovada pelo filtro\n{title}\nPreço informado: R$ {price:.2f}" + (f"\nLink: {link}" if link else "\nLink: não detectado; confira a mensagem encaminhada.")
    dest = db.get_setting(uid, "forward_destination")
    if dest:
        try:
            await context.bot.copy_message(chat_id=int(dest), from_chat_id=msg.chat_id, message_id=msg.message_id)
            await context.bot.send_message(chat_id=int(dest), text=summary, disable_web_page_preview=False)
            if reply_to_user: await msg.reply_text("Oferta aprovada e publicada no grupo de destino.")
        except Exception as exc:
            log.warning("Falha ao publicar encaminhamento (%s)", type(exc).__name__)
            if reply_to_user: await msg.reply_text("A oferta passou pelos filtros, mas não consegui publicar no grupo. Verifique se o bot ainda pode enviar mensagens nele.")
    else:
        if reply_to_user: await msg.reply_text(summary + "\n\nPara publicar automaticamente em um grupo, configure /destino nele.", disable_web_page_preview=False)


async def group_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update, context): return
    db, args = context.application.bot_data["db"], context.args
    if not args or args[0].lower() == "listar":
        rows = db.monitored_groups()
        await update.effective_message.reply_text("Grupos monitorados:\n" + ("\n".join(f"• {r['chat_ref']} — {'ativo' if r['active'] else 'pausado'}" for r in rows) or "nenhum")); return
    if len(args) < 2:
        await update.effective_message.reply_text("Uso: /grupo add @grupo | remover @grupo | pausar @grupo | retomar @grupo"); return
    action, ref = args[0].lower(), args[1].strip()
    if action == "add":
        db.add_monitored_group(ref, update.effective_user.id); msg = f"Grupo {ref} cadastrado; o coletor tentará conectar-se com sua conta autorizada."
    elif action == "remover": msg = "Grupo removido." if db.remove_monitored_group(ref) else "Grupo não encontrado."
    elif action in ("pausar", "retomar"):
        msg = "Atualizado." if db.set_group_active(ref, action == "retomar") else "Grupo não encontrado."
    else: msg = "Ações: add, remover, pausar, retomar, listar."
    await update.effective_message.reply_text(msg)


async def groups_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update, context): return
    rows = context.application.bot_data["db"].monitored_groups()
    await update.effective_message.reply_text("Grupos monitorados:\n" + ("\n".join(f"• {r['chat_ref']} — {'ativo' if r['active'] else 'pausado'}" for r in rows) or "nenhum"))


async def score_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update, context): return
    db, uid = context.application.bot_data["db"], update.effective_user.id
    if not context.args:
        await update.effective_message.reply_text(f"Score mínimo atual: {db.get_setting(uid, 'hunter_min_score') or '70'}"); return
    try: value = int(context.args[0])
    except ValueError: value = -1
    if not 0 <= value <= 100:
        await update.effective_message.reply_text("Use /score 70, com valor de 0 a 100."); return
    db.set_setting(uid, "hunter_min_score", str(value)); await update.effective_message.reply_text(f"Score mínimo definido: {value}.")


async def categories_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update, context): return
    db, uid = context.application.bot_data["db"], update.effective_user.id
    value = " ".join(context.args).strip()
    if value: db.set_setting(uid, "hunter_categories", value)
    await update.effective_message.reply_text(f"Categorias: {db.get_setting(uid, 'hunter_categories') or 'todas'}. Use /categorias gpu,cpu,ssd,ram,fonte,monitor,periférico,outros.")


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update, context): return
    stats = context.application.bot_data["db"].collected_stats()
    await update.effective_message.reply_text("Total: {total}\nAguardando publicação: {approved}\nPublicadas: {published}\nDescartadas: {rejected}\nRevisão: {review}".format(**{k: stats.get(k, 0) for k in ("total", "approved", "published", "rejected", "review")}))


async def collected_list(update: Update, context: ContextTypes.DEFAULT_TYPE, decision: str) -> None:
    if not await guard(update, context): return
    rows = context.application.bot_data["db"].collected(decision, 10)
    await update.effective_message.reply_text("\n\n".join(f"ID {r['id']} · {r['source_title']} · score {r['hunter_score']}\n{r['text'][:200]}" for r in rows) or "Nenhuma mensagem nesta categoria.")


async def rejected_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None: await collected_list(update, context, "rejected")
async def review_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None: await collected_list(update, context, "review")
async def published_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None: await collected_list(update, context, "published")


async def approve_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update, context): return
    if not context.args or not context.args[0].isdigit():
        await update.effective_message.reply_text("Uso: /aprovar ID (consulte /revisao)."); return
    ok = context.application.bot_data["db"].set_collected_decision(int(context.args[0]), "approved")
    await update.effective_message.reply_text("Aprovado para publicação." if ok else "ID não encontrado.")


def build_application(settings: Settings, db: Database) -> Application:
    app = Application.builder().token(settings.telegram_bot_token).build()
    app.bot_data.update(settings=settings, db=db, notifications_enabled=True)
    handlers = {
        "start": start, "help": help_command, "pesquisar": search_command, "adicionar": add_watch,
        "remover": remove_watch, "watchlist": watchlist, "ofertas": offers, "achadinhos": bargains,
        "gpu": category_search("placa de vídeo"), "cpu": category_search("processador"),
        "ram": category_search("memória RAM"), "ssd": category_search("SSD"),
        "fontes": category_search("fonte ATX"), "mouse": category_search("mouse"),
        "monitor": category_search("monitor"), "kits": category_search("kit upgrade PC"),
        "historico": history, "precos": history, "ranking": offers, "favoritos": favorite_list,
        "config": config, "status": status, "pausar": pause, "retomar": resume,
        "limpar": clear_prompt, "filtro": filter_command, "destino": set_destination, "origem": set_source,
        "grupo": group_admin, "grupos": groups_command, "score": score_command, "categorias": categories_command,
        "estatisticas": stats_command, "descartadas": rejected_command, "revisao": review_command,
        "publicadas": published_command, "aprovar": approve_command,
    }
    for command, handler in handlers.items(): app.add_handler(CommandHandler(command, handler))
    app.add_handler(CommandHandler("revenda", lambda u, c: misc_command(u, c, "Modo revenda: desativado. Uma estimativa confiável exige pelo menos 3 preços comparáveis observados; nenhuma margem é garantida.")))
    app.add_handler(CommandHandler("resumo", offers))
    app.add_handler(CallbackQueryHandler(clear_callback, pattern=r"^clear:"))
    app.add_handler(CallbackQueryHandler(callback, pattern=r"^(fav|ignore):"))
    app.add_handler(MessageHandler((filters.ChatType.GROUPS) & ~filters.COMMAND, source_group_message))
    app.add_handler(MessageHandler(filters.FORWARDED & ~filters.COMMAND, forwarded_offer))
    install_jobs(app)
    return app

