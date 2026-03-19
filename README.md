# 🤖 Telegram AI Bot — OpenRouter

Полностью бесплатный Telegram-бот с ИИ на базе OpenRouter.
**Работает из России без VPN.**

---

## ✨ Возможности

| | |
|---|---|
| 💬 Групповые чаты | Отвечает на @упоминания и реплаи |
| 🔍 Инлайн-режим | `@бот запрос` в любом чате |
| 🌐 Поиск в интернете | Через :online модели OpenRouter |
| 🧠 Постоянная память | Долгосрочные факты (никогда не удаляются) |
| 📝 Гибкий промпт | Переменные, кастомные значения в config.yaml |
| 🔓 Без фильтров | Управляешь сам через промпт |

---

## 🚀 Деплой на Railway

### 1. Получи токены

**Telegram Bot:**
- [@BotFather](https://t.me/BotFather) → `/newbot` → `/setprivacy` Disable → `/setinline` Enable
- [@userinfobot](https://t.me/userinfobot) — узнай свой Telegram ID

**OpenRouter API Key (бесплатно, работает из России):**
1. Зайди на [openrouter.ai](https://openrouter.ai) — регистрация через email или GitHub
2. Keys → Create Key
3. Карта не нужна, лимиты на бесплатные модели не требуют баланса

### 2. Загрузи код на GitHub
```bash
git init && git add . && git commit -m "init"
git remote add origin https://github.com/ты/репо.git
git push -u origin main
```

### 3. Railway
1. [railway.app](https://railway.app) → New Project → GitHub Repo
2. Variables → добавь:
   ```
   TELEGRAM_TOKEN     = ...
   OPENROUTER_API_KEY = ...
   ADMIN_IDS          = твой_id
   WEBHOOK_URL        = (пока пусто)
   ```
3. Settings → Networking → **Generate Domain** → скопируй URL
4. Вставь URL в `WEBHOOK_URL`

### 4. Постоянная память (Volume)
- Railway → Add Service → Volume → Mount Path: `/data`
- Добавь переменную: `DB_PATH=/data/bot_memory.db`

---

## 📝 config.yaml — центр управления

Весь конфиг в одном файле. Редактируй — Python не трогай.

### Промпт с переменными
```yaml
system_prompt: |
  Ты {custom.bot_name}. Сегодня {date}, {time}.
  Пользователь: {user_name}. Чат: {chat_title}.
  {long_term}
  Отвечай кратко.
```

**Переменные:**
| | |
|---|---|
| `{user_name}` | Имя пользователя |
| `{chat_title}` | Название чата |
| `{date}` / `{time}` | Дата и время |
| `{long_term}` | Блок долгосрочной памяти |
| `{custom.имя}` | Свои переменные |

### Кастомные переменные
```yaml
custom_vars:
  bot_name: "Макс"
  tone: "дружелюбный"
  topic: "программирование"
```

### Условия долгосрочной памяти
```yaml
memory:
  save_conditions:
    - "имя пользователя"
    - "профессия и навыки"
    - "предпочтения"
    # добавляй свои...
```

### Поиск
```yaml
search:
  enabled: true   # false — отключить
```

---

## 📋 Команды бота

| Команда | Кто | |
|---------|-----|-|
| `/start` | Все | Справка |
| `/clear` | Все | Очистить историю (память сохраняется) |
| `/prompt` | Все | Показать промпт |
| `/setprompt <текст>` | Админы | Переопределить промпт |
| `/resetprompt` | Админы | Сбросить на config.yaml |
| `/model` | Все | Текущая модель |
| `/setmodel <id>` | Bot Admin | Сменить модель |
| `/memory` | Все | Долгосрочная память о себе |
| `/forget <id>` | Все | Удалить факт |
| `/forgetme` | Все | Стереть всю память о себе |

---

## 🤖 Лучшие бесплатные модели OpenRouter

| Модель | Описание |
|--------|---------|
| `deepseek/deepseek-chat-v3-0324:free` | Быстрая и умная ✅ дефолт |
| `deepseek/deepseek-r1:free` | Думающая 🔥 как o1, медленнее |
| `meta-llama/llama-4-maverick:free` | Мощная от Meta |
| `meta-llama/llama-4-scout:free` | Быстрая от Meta |
| `google/gemma-3-27b-it:free` | От Google, без геоблока |
| `mistralai/mistral-small-3.1-24b-instruct:free` | Стабильная |

Полный список: [openrouter.ai/models?q=:free](https://openrouter.ai/models?q=:free)

---

## 🧠 Как работает долгосрочная память

1. После каждого ответа — отдельный лёгкий вызов API анализирует разговор
2. Найденные факты сохраняются в SQLite таблицу `long_term`
3. При следующем разговоре все факты вставляются в промпт через `{long_term}`
4. **Никогда не удаляются автоматически** — только `/forget` или `/forgetme`
5. Условия что считать важным — в `config.yaml` → `memory.save_conditions`

---

## 📁 Структура
```
├── bot.py         — команды, webhook, обработка
├── ai.py          — OpenRouter API, поиск, извлечение фактов
├── db.py          — SQLite (история, долгосрочная память, настройки)
├── config.py      — загрузчик config.yaml
├── config.yaml    — ВСЯ ЛОГИКА И НАСТРОЙКИ ЗДЕСЬ
├── .env.example
├── Dockerfile
├── railway.toml
└── requirements.txt
```
