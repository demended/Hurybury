"""
Telegram AI Bot — Google Gemini 2.5 Pro
  • Поиск в интернете (Google Search Grounding)
  • Постоянная долгосрочная память
  • Конфигурация через config.yaml
  • Webhook для Railway / Render
"""

import os
import logging
from datetime import datetime

from telegram import (
    Update,
    InlineQueryResultArticle,
    InputTextMessageContent,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    InlineQueryHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ParseMode
from dotenv import load_dotenv

from db import Database
from ai import ask_ai, extract_facts
from config import load_config

load_dotenv()
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─── Обязательные env переменные ──────────────────────────────
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
WEBHOOK_URL    = os.environ["WEBHOOK_URL"]
PORT           = int(os.getenv("PORT", "8080"))

ADMIN_IDS = set(
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip()
)

db = Database()


# ─── Утилиты ──────────────────────────────────────────────────

def get_context(update: Update) -> dict:
    """Собирает контекст для подстановки переменных в промпт."""
    user = update.effective_user
    chat = update.effective_chat
    now  = datetime.now()
    return {
        "user_name":  user.first_name if user else "Пользователь",
        "chat_title": chat.title or "личный чат",
        "date":       now.strftime("%d.%m.%Y"),
        "time":       now.strftime("%H:%M"),
    }


def get_system_prompt_raw(chat_id) -> str:
    """Берёт промпт из БД (если задан через /setprompt) или из config.yaml."""
    db_prompt = db.get_system_prompt(chat_id)
    if db_prompt:
        return db_prompt
    cfg = load_config()
    return cfg.get("system_prompt", "Ты умный ассистент. Отвечай на языке пользователя.")


def is_bot_addressed(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    msg = update.message
    if not msg:
        return False
    if update.effective_chat.type == "private":
        return True
    if msg.reply_to_message and msg.reply_to_message.from_user:
        if msg.reply_to_message.from_user.id == ctx.bot.id:
            return True
    if msg.entities:
        for entity in msg.entities:
            if entity.type == "mention":
                mention = msg.text[entity.offset: entity.offset + entity.length]
                if mention.lower() == f"@{ctx.bot.username}".lower():
                    return True
    return False


def strip_mention(text: str, username: str) -> str:
    return text.replace(f"@{username}", "").strip()


# ─── Команды ──────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    cfg  = load_config()
    bot_name = cfg.get("custom_vars", {}).get("bot_name", "ИИ-бот")
    await update.message.reply_text(
        f"Привет, {user.first_name}! 👋 Я *{bot_name}* на базе Google Gemini.\n\n"
        "📌 *Использование:*\n"
        "• Личка — просто пиши\n"
        "• Группа — @упомяни меня или сделай реплай\n"
        "• Инлайн — `@бот запрос` в любом чате\n\n"
        "⚙️ *Команды:*\n"
        "/start — справка\n"
        "/clear — очистить историю диалога\n"
        "/prompt — показать системный промпт\n"
        "/setprompt `<текст>` — изменить промпт\n"
        "/resetprompt — сбросить на конфиг\n"
        "/model — текущая модель\n"
        "/setmodel `<id>` — сменить модель _(Admin)_\n\n"
        "🧠 *Долгосрочная память:*\n"
        "/memory — посмотреть что я о тебе помню\n"
        "/forgetme — стереть всю мою память о тебе\n"
        "/forget `<id>` — стереть конкретный факт",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_clear(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db.clear_history(update.effective_chat.id)
    await update.message.reply_text(
        "🗑 История диалога очищена.\n"
        "_Долгосрочная память сохранена._",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_prompt(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    db_prompt = db.get_system_prompt(chat_id)
    cfg = load_config()
    config_prompt = cfg.get("system_prompt", "")

    if db_prompt:
        source = "_(переопределён через /setprompt)_"
        prompt_text = db_prompt
    else:
        source = "_(из config.yaml)_"
        prompt_text = config_prompt

    await update.message.reply_text(
        f"📋 *Системный промпт* {source}:\n\n`{prompt_text}`",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_setprompt(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    cfg     = load_config()

    if update.effective_chat.type in ("group", "supergroup"):
        if cfg.get("groups", {}).get("admin_only_setprompt", True):
            member = await ctx.bot.get_chat_member(chat_id, user_id)
            if member.status not in ("administrator", "creator") and user_id not in ADMIN_IDS:
                await update.message.reply_text("❌ Только администраторы могут менять промпт.")
                return

    new_prompt = " ".join(ctx.args)
    if not new_prompt:
        await update.message.reply_text(
            "Использование: `/setprompt <текст промпта>`\n\n"
            "Доступные переменные: `{user_name}`, `{chat_title}`, `{date}`, `{time}`, `{long_term}`, `{custom.имя}`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    db.set_system_prompt(chat_id, new_prompt)
    await update.message.reply_text(
        f"✅ Промпт обновлён:\n\n`{new_prompt}`",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_resetprompt(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db.set_system_prompt(update.effective_chat.id, None)  # None = брать из config.yaml
    cfg = load_config()
    prompt = cfg.get("system_prompt", "")
    await update.message.reply_text(
        f"✅ Промпт сброшен на значение из `config.yaml`:\n\n`{prompt}`",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_model(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    model = db.get_model(update.effective_chat.id)
    cfg   = load_config()
    default = cfg.get("model", {}).get("default", "—")
    await update.message.reply_text(
        f"🤖 *Текущая модель:* `{model}`\n"
        f"_(дефолт в config.yaml: `{default}`)_",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_setmodel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Только Bot Admin может менять модель.")
        return

    model = " ".join(ctx.args)
    if not model:
        await update.message.reply_text(
            "Использование: `/setmodel <model_id>`\n\n"
            "*Лучшие бесплатные модели OpenRouter:*\n"
            "• `deepseek/deepseek-chat-v3-0324:free` — быстрая и умная ✅\n"
            "• `deepseek/deepseek-r1:free` — думающая 🔥 (медленнее)\n"
            "• `meta-llama/llama-4-maverick:free` — мощная от Meta\n"
            "• `google/gemma-3-27b-it:free` — от Google\n"
            "_Все модели работают из России без VPN_",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    db.set_model(update.effective_chat.id, model)
    await update.message.reply_text(f"✅ Модель: `{model}`", parse_mode=ParseMode.MARKDOWN)


# ── Команды долгосрочной памяти ──────────────────────────────

async def cmd_memory(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    facts   = db.get_long_term_with_ids(chat_id, user_id)

    if not facts:
        await update.message.reply_text("🧠 Долгосрочная память о тебе пуста.")
        return

    lines = [f"`[{fid}]` {fact}" for fid, fact, _ in facts]
    text  = "🧠 *Что я о тебе помню:*\n\n" + "\n".join(lines)
    text += "\n\n_Удалить факт: /forget `<id>`_"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def cmd_forgetme(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    db.clear_long_term(chat_id, user_id)
    await update.message.reply_text("🗑 Вся долгосрочная память о тебе удалена.")


async def cmd_forget(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Использование: /forget `<id>`", parse_mode=ParseMode.MARKDOWN)
        return
    try:
        fact_id = int(ctx.args[0])
        db.delete_long_term_fact(fact_id)
        await update.message.reply_text(f"✅ Факт #{fact_id} удалён.")
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом.")


# ─── Обработка сообщений ──────────────────────────────────────

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    if not is_bot_addressed(update, ctx):
        return

    chat_id = update.effective_chat.id
    user    = update.effective_user
    text    = strip_mention(update.message.text, ctx.bot.username)

    if not text:
        await update.message.reply_text("Напиши что-нибудь 😊")
        return

    await ctx.bot.send_chat_action(chat_id=chat_id, action="typing")

    cfg           = load_config()
    model         = db.get_model(chat_id)
    history       = db.get_history(chat_id)
    long_term     = db.get_long_term_facts(chat_id, user.id)
    context       = get_context(update)
    system_raw    = get_system_prompt_raw(chat_id)

    user_label = user.first_name or "User"
    user_msg   = f"{user_label}: {text}"
    db.add_message(chat_id, "user", user_msg)
    history.append({"role": "user", "content": user_msg})

    reply = await ask_ai(system_raw, history, model, context, long_term)
    db.add_message(chat_id, "assistant", reply)

    await update.message.reply_text(reply)

    # Асинхронно извлекаем факты для долгосрочной памяти
    if cfg.get("memory", {}).get("long_term_enabled", True):
        facts = await extract_facts(text, reply, cfg)
        for fact in facts:
            db.add_long_term_fact(chat_id, user.id, fact)
            logger.info(f"Saved long-term fact for user {user.id}: {fact}")


# ─── Инлайн режим ─────────────────────────────────────────────

async def handle_inline(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query.strip()
    if not query:
        return

    user_id    = update.inline_query.from_user.id
    inline_key = f"inline_{user_id}"
    cfg        = load_config()
    model      = db.get_model(inline_key)
    history    = db.get_history(inline_key)
    long_term  = db.get_long_term_facts(inline_key, user_id)
    system_raw = get_system_prompt_raw(inline_key)

    context = {
        "user_name":  update.inline_query.from_user.first_name or "Пользователь",
        "chat_title": "инлайн-запрос",
        "date":       datetime.now().strftime("%d.%m.%Y"),
        "time":       datetime.now().strftime("%H:%M"),
    }

    history.append({"role": "user", "content": query})
    reply = await ask_ai(system_raw, history, model, context, long_term)

    results = [
        InlineQueryResultArticle(
            id="1",
            title="✨ Ответ Gemini",
            description=reply[:120] + ("…" if len(reply) > 120 else ""),
            input_message_content=InputTextMessageContent(
                message_text=f"❓ *{query}*\n\n{reply}",
                parse_mode=ParseMode.MARKDOWN,
            ),
        )
    ]
    await update.inline_query.answer(results, cache_time=10)


# ─── Запуск ───────────────────────────────────────────────────

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Команды
    app.add_handler(CommandHandler("start",       cmd_start))
    app.add_handler(CommandHandler("clear",       cmd_clear))
    app.add_handler(CommandHandler("prompt",      cmd_prompt))
    app.add_handler(CommandHandler("setprompt",   cmd_setprompt))
    app.add_handler(CommandHandler("resetprompt", cmd_resetprompt))
    app.add_handler(CommandHandler("model",       cmd_model))
    app.add_handler(CommandHandler("setmodel",    cmd_setmodel))
    # Долгосрочная память
    app.add_handler(CommandHandler("memory",      cmd_memory))
    app.add_handler(CommandHandler("forgetme",    cmd_forgetme))
    app.add_handler(CommandHandler("forget",      cmd_forget))

    # Сообщения и инлайн
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(InlineQueryHandler(handle_inline))

    webhook_path = f"/webhook/{TELEGRAM_TOKEN}"
    logger.info(f"Starting on :{PORT}, webhook: {WEBHOOK_URL}{webhook_path}")

    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=webhook_path,
        webhook_url=f"{WEBHOOK_URL}{webhook_path}",
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
