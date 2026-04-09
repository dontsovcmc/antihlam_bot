import sqlite3
import time
from log import logger


class DatabaseManager:
    def __init__(self, db_path):
        self.db_path = db_path
        self._init_tables()

    def _init_tables(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.executescript('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_user_id INTEGER UNIQUE NOT NULL,
                    avito_user_id TEXT,
                    access_token TEXT,
                    refresh_token TEXT,
                    token_expires_at INTEGER DEFAULT 0,
                    browser_session_valid INTEGER DEFAULT 0,
                    created_at INTEGER
                );

                CREATE TABLE IF NOT EXISTS ads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    avito_ad_id TEXT,
                    avito_url TEXT,
                    title TEXT,
                    description TEXT,
                    price INTEGER,
                    category TEXT,
                    photo_path TEXT,
                    status TEXT DEFAULT 'draft',
                    created_at INTEGER,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    avito_chat_id TEXT,
                    avito_ad_id TEXT,
                    telegram_message_id INTEGER,
                    direction TEXT,
                    text TEXT,
                    timestamp INTEGER,
                    created_at INTEGER,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );
            ''')

    def get_or_create_user(self, telegram_user_id: int) -> int:
        """Возвращает id пользователя, создаёт если не существует."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT id FROM users WHERE telegram_user_id = ?', (telegram_user_id,))
            result = cursor.fetchone()
            if result:
                return result[0]
            cursor.execute(
                'INSERT INTO users (telegram_user_id, created_at) VALUES (?, ?)',
                (telegram_user_id, int(time.time()))
            )
            return cursor.lastrowid

    def get_user_by_telegram_id(self, telegram_user_id: int) -> dict | None:
        """Возвращает данные пользователя по telegram_user_id."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE telegram_user_id = ?', (telegram_user_id,))
            result = cursor.fetchone()
            return dict(result) if result else None

    def update_user_tokens(self, telegram_user_id: int, access_token: str, refresh_token: str, expires_at: int):
        """Обновляет OAuth токены пользователя."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users SET access_token = ?, refresh_token = ?, token_expires_at = ?
                WHERE telegram_user_id = ?
            ''', (access_token, refresh_token, expires_at, telegram_user_id))

    def update_browser_session(self, telegram_user_id: int, valid: bool):
        """Обновляет статус браузерной сессии."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                'UPDATE users SET browser_session_valid = ? WHERE telegram_user_id = ?',
                (1 if valid else 0, telegram_user_id)
            )

    def create_ad(self, user_id: int, title: str, description: str, price: int,
                  category: str, photo_path: str) -> int:
        """Создаёт запись объявления со статусом draft."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO ads (user_id, title, description, price, category, photo_path, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'draft', ?)
            ''', (user_id, title, description, price, category, photo_path, int(time.time())))
            return cursor.lastrowid

    def update_ad_status(self, ad_id: int, status: str, avito_ad_id: str = None, avito_url: str = None):
        """Обновляет статус объявления."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            if avito_ad_id and avito_url:
                cursor.execute(
                    'UPDATE ads SET status = ?, avito_ad_id = ?, avito_url = ? WHERE id = ?',
                    (status, avito_ad_id, avito_url, ad_id)
                )
            else:
                cursor.execute('UPDATE ads SET status = ? WHERE id = ?', (status, ad_id))

    def update_ad_price(self, ad_id: int, price: int):
        """Обновляет цену объявления."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE ads SET price = ? WHERE id = ?', (price, ad_id))

    def update_ad_description(self, ad_id: int, description: str):
        """Обновляет описание объявления."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE ads SET description = ? WHERE id = ?', (description, ad_id))

    def get_user_ads(self, user_id: int, limit: int = 10) -> list[dict]:
        """Возвращает последние объявления пользователя."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                'SELECT * FROM ads WHERE user_id = ? ORDER BY created_at DESC LIMIT ?',
                (user_id, limit)
            )
            return [dict(row) for row in cursor.fetchall()]

    def save_message(self, user_id: int, avito_chat_id: str, avito_ad_id: str,
                     telegram_message_id: int, direction: str, text: str, timestamp: int):
        """Сохраняет сообщение (входящее или исходящее)."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO messages (user_id, avito_chat_id, avito_ad_id, telegram_message_id, direction, text, timestamp, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, avito_chat_id, avito_ad_id, telegram_message_id, direction, text, timestamp, int(time.time())))

    def get_message_by_telegram_id(self, telegram_message_id: int) -> dict | None:
        """Находит сообщение по telegram_message_id для ответа."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                'SELECT * FROM messages WHERE telegram_message_id = ?',
                (telegram_message_id,)
            )
            result = cursor.fetchone()
            return dict(result) if result else None


db_manager = DatabaseManager('antihlam_bot.db')
