"""
OpenRouter API клиент
  — Работает из России без VPN
  — Поиск в интернете через веб-инструмент (модели с :online суффиксом)
  — Извлечение фактов для долгосрочной памяти
  — OpenAI-совместимый формат запросов
"""

import os
import json
import logging
import httpx
from config import load_config

logger = logging.getLogger(__name__)

OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Заголовки рекомендованные OpenRouter
HEADERS = {
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "Content-Type": "application/json",
    "HTTP-Referer": os.getenv("SITE_URL", "https://t.me/mybot"),
    "X-Title": os.getenv("BOT_NAME", "Telegram AI Bot"),
}


def _render_system_prompt(raw_prompt: str, context: dict, long_term_facts: list[str], cfg: dict) -> str:
    """Подставляет переменные в системный промпт."""
    if long_term_facts and cfg.get("memory", {}).get("long_term_enabled", True):
        facts_text = "\n".join(f"- {f}" for f in long_term_facts)
        template = cfg.get("long_term_template", "## Долгосрочная память\n{facts}\n---\n")
        long_term_block = template.replace("{facts}", facts_text)
    else:
        long_term_block = ""

    custom_vars = cfg.get("custom_vars", {})

    result = raw_prompt
    result = result.replace("{long_term}", long_term_block)
    result = result.replace("{user_name}",  context.get("user_name", "Пользователь"))
    result = result.replace("{chat_title}", context.get("chat_title", "чат"))
    result = result.replace("{date}",       context.get("date", ""))
    result = result.replace("{time}",       context.get("time", ""))

    for key, val in custom_vars.items():
        result = result.replace(f"{{custom.{key}}}", str(val))

    return result


def _get_model_for_request(model: str, cfg: dict) -> str:
    """
    Если в config включён поиск — добавляет суффикс :online к модели.
    Модели с :online на OpenRouter автоматически ищут в интернете.
    Некоторые модели уже имеют встроенный поиск — для них суффикс не нужен.
    """
    search_enabled = cfg.get("search", {}).get("enabled", False)
    if search_enabled and ":online" not in model and ":free" in model:
        # Заменяем :free на :online — OpenRouter поддерживает оба суффикса
        return model.replace(":free", ":online")
    return model


async def ask_ai(
    system_prompt_raw: str,
    history: list[dict],
    model: str,
    context: dict,
    long_term_facts: list[str],
) -> str:
    """Основной запрос к OpenRouter."""
    cfg = load_config()
    system_prompt = _render_system_prompt(system_prompt_raw, context, long_term_facts, cfg)
    model_cfg = cfg.get("model", {})

    # Собираем сообщения: system + история
    messages = [{"role": "system", "content": system_prompt}] + history

    # Определяем модель (с поиском или без)
    actual_model = _get_model_for_request(model, cfg)

    payload = {
        "model": actual_model,
        "messages": messages,
        "max_tokens": model_cfg.get("max_output_tokens", 2048),
        "temperature": model_cfg.get("temperature", 0.9),
    }

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(OPENROUTER_URL, json=payload, headers=HEADERS)
            resp.raise_for_status()
            data = resp.json()

        content = data["choices"][0]["message"]["content"]
        return content.strip() if content else "Не удалось получить ответ."

    except httpx.HTTPStatusError as e:
        logger.error(f"OpenRouter HTTP {e.response.status_code}: {e.response.text}")
        if e.response.status_code == 429:
            return "⏳ Превышен лимит запросов. Подожди минуту и попробуй снова."
        if e.response.status_code == 402:
            return "❌ Кредиты на аккаунте OpenRouter закончились. Проверь баланс."
        if e.response.status_code == 401:
            return "❌ Неверный API ключ OpenRouter. Проверь переменную OPENROUTER_API_KEY."
        return f"❌ Ошибка API ({e.response.status_code})."

    except Exception as e:
        logger.error(f"OpenRouter error: {e}")
        return "❌ Ошибка при обращении к ИИ. Попробуй позже."


async def extract_facts(user_message: str, bot_reply: str, cfg: dict) -> list[str]:
    """
    Лёгкий вызов для извлечения фактов в долгосрочную память.
    Использует самую быструю бесплатную модель чтобы не тратить лимиты основной.
    """
    conditions = cfg.get("memory", {}).get("save_conditions", [])
    if not conditions:
        return []

    conditions_text = "\n".join(f"- {c}" for c in conditions)
    extraction_model = cfg.get("memory", {}).get("extraction_model", "deepseek/deepseek-chat-v3-0324:free")

    extraction_prompt = f"""Проанализируй сообщение пользователя и ответ ассистента.
Извлеки ТОЛЬКО важные факты о пользователе, которые стоит запомнить навсегда.

Сохраняй факт если он относится к одной из категорий:
{conditions_text}

Сообщение пользователя: {user_message}
Ответ ассистента: {bot_reply}

Ответь ТОЛЬКО в формате JSON массива строк. Пример: ["Пользователя зовут Иван", "Любит Python"]
Если фактов нет — ответь: []
Никакого другого текста, никаких markdown блоков."""

    payload = {
        "model": extraction_model,
        "messages": [{"role": "user", "content": extraction_prompt}],
        "max_tokens": 512,
        "temperature": 0.1,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(OPENROUTER_URL, json=payload, headers=HEADERS)
            resp.raise_for_status()
            data = resp.json()

        text = data["choices"][0]["message"]["content"].strip()
        text = text.replace("```json", "").replace("```", "").strip()

        facts = json.loads(text)
        return [f for f in facts if isinstance(f, str) and f.strip()]

    except Exception as e:
        logger.warning(f"Fact extraction failed: {e}")
        return []
