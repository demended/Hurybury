"""
База данных — SQLite
Таблицы:
  history       — скользящая история диалога (чистится по MAX_HISTORY)
  long_term     — постоянная память (никогда не удаляется автоматически)
  chat_settings — промпт и модель для каждого чата
"""

import sqlite3
import os
from typing import Optional
from config import load_config

DB_PATH = os.getenv("DB_PATH", "bot_memory.db")


class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self._init_tables()

    def _init_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS history (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT    NOT NULL,
                role    TEXT    NOT NULL,
                content TEXT    NOT NULL,
                ts      DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS long_term (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT    NOT NULL,
                user_id TEXT    NOT NULL,
                fact    TEXT    NOT NULL,
                ts      DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS chat_settings (
                chat_id       TEXT PRIMARY KEY,
                system_prompt TEXT,
                model         TEXT
            );
        """)
        self.conn.commit()

    # ── Краткосрочная история ──────────────────────────────────

    def add_message(self, chat_id, role: str, content: str):
        chat_id = str(chat_id)
        self.conn.execute(
            "INSERT INTO history (chat_id, role, content) VALUES (?, ?, ?)",
            (chat_id, role, content),
        )
        self.conn.commit()
        cfg = load_config()
        max_h = cfg.get("memory", {}).get("max_history", 60)
        self._trim_history(chat_id, max_h)

    def _trim_history(self, chat_id: str, limit: int):
        self.conn.execute(
            """
            DELETE FROM history
            WHERE chat_id = ?
              AND id NOT IN (
                SELECT id FROM history
                WHERE chat_id = ?
                ORDER BY id DESC
                LIMIT ?
              )
            """,
            (chat_id, chat_id, limit),
        )
        self.conn.commit()

    def get_history(self, chat_id) -> list[dict]:
        chat_id = str(chat_id)
        cur = self.conn.execute(
            "SELECT role, content FROM history WHERE chat_id = ? ORDER BY id ASC",
            (chat_id,),
        )
        return [{"role": row[0], "content": row[1]} for row in cur.fetchall()]

    def clear_history(self, chat_id):
        """Чистит только краткосрочную историю. Долгосрочная память не трогается."""
        self.conn.execute("DELETE FROM history WHERE chat_id = ?", (str(chat_id),))
        self.conn.commit()

    # ── Долгосрочная память ────────────────────────────────────

    def add_long_term_fact(self, chat_id, user_id, fact: str):
        """Добавить факт в постоянную память."""
        self.conn.execute(
            "INSERT INTO long_term (chat_id, user_id, fact) VALUES (?, ?, ?)",
            (str(chat_id), str(user_id), fact),
        )
        self.conn.commit()

    def get_long_term_facts(self, chat_id, user_id) -> list[str]:
        """Получить все факты о пользователе в данном чате."""
        cur = self.conn.execute(
            "SELECT fact FROM long_term WHERE chat_id = ? AND user_id = ? ORDER BY id ASC",
            (str(chat_id), str(user_id)),
        )
        return [row[0] for row in cur.fetchall()]

    def delete_long_term_fact(self, fact_id: int):
        """Удалить конкретный факт по ID (для ручного управления)."""
        self.conn.execute("DELETE FROM long_term WHERE id = ?", (fact_id,))
        self.conn.commit()

    def get_long_term_with_ids(self, chat_id, user_id) -> list[tuple]:
        """Вернуть факты с ID для команды /memory."""
        cur = self.conn.execute(
            "SELECT id, fact, ts FROM long_term WHERE chat_id = ? AND user_id = ? ORDER BY id ASC",
            (str(chat_id), str(user_id)),
        )
        return cur.fetchall()

    def clear_long_term(self, chat_id, user_id):
        """Полностью очистить долгосрочную память пользователя."""
        self.conn.execute(
            "DELETE FROM long_term WHERE chat_id = ? AND user_id = ?",
            (str(chat_id), str(user_id)),
        )
        self.conn.commit()

    # ── Настройки чата ─────────────────────────────────────────

    def _ensure(self, chat_id: str):
        self.conn.execute(
            "INSERT OR IGNORE INTO chat_settings (chat_id) VALUES (?)", (chat_id,)
        )
        self.conn.commit()

    def get_system_prompt(self, chat_id) -> Optional[str]:
        chat_id = str(chat_id)
        self._ensure(chat_id)
        row = self.conn.execute(
            "SELECT system_prompt FROM chat_settings WHERE chat_id = ?", (chat_id,)
        ).fetchone()
        return row[0] if row else None

    def set_system_prompt(self, chat_id, prompt: str):
        chat_id = str(chat_id)
        self._ensure(chat_id)
        self.conn.execute(
            "UPDATE chat_settings SET system_prompt = ? WHERE chat_id = ?",
            (prompt, chat_id),
        )
        self.conn.commit()

    def get_model(self, chat_id) -> str:
        chat_id = str(chat_id)
        self._ensure(chat_id)
        row = self.conn.execute(
            "SELECT model FROM chat_settings WHERE chat_id = ?", (chat_id,)
        ).fetchone()
        cfg = load_config()
        default = cfg.get("model", {}).get("default", "gemini-2.5-pro-exp-03-25")
        return row[0] if row and row[0] else default

    def set_model(self, chat_id, model: str):
        chat_id = str(chat_id)
        self._ensure(chat_id)
        self.conn.execute(
            "UPDATE chat_settings SET model = ? WHERE chat_id = ?",
            (model, chat_id),
        )
        self.conn.commit()
