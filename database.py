import sqlite3
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any


class Database:
    """Работа с SQLite базой данных для парсера отзывов WB"""

    def __init__(self, db_path: str = "bot_data.db"):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """Инициализация базы данных и создание таблиц"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Таблица пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_requests INTEGER DEFAULT 0
            )
        ''')

        # Таблица запросов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                marketplace TEXT,
                product_url TEXT,
                reviews_count INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                success INTEGER DEFAULT 1,
                error_message TEXT,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')

        # Таблица rate limits
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rate_limits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')

        # Миграция: добавляем новые колонки, если их ещё нет (старая БД)
        cursor.execute("PRAGMA table_info(requests)")
        existing_cols = {row[1] for row in cursor.fetchall()}
        new_cols = {
            'filter_type': "TEXT",
            'questions_count': "INTEGER DEFAULT 0",
            'avg_rating': "REAL DEFAULT 0",
            'reviews_file_id': "TEXT",
            'questions_file_id': "TEXT",
        }
        for col, decl in new_cols.items():
            if col not in existing_cols:
                cursor.execute(f"ALTER TABLE requests ADD COLUMN {col} {decl}")

        conn.commit()
        conn.close()

    def add_or_update_user(
        self,
        user_id: int,
        username: str = None,
        first_name: str = None,
        last_name: str = None
    ):
        """Добавляет нового пользователя или обновляет существующего"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO users (user_id, username, first_name, last_name, first_seen, last_activity)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                username = COALESCE(excluded.username, users.username),
                first_name = COALESCE(excluded.first_name, users.first_name),
                last_name = COALESCE(excluded.last_name, users.last_name),
                last_activity = CURRENT_TIMESTAMP
        ''', (user_id, username, first_name, last_name))

        conn.commit()
        conn.close()

    def add_request(
        self,
        user_id: int,
        marketplace: str,
        product_url: str,
        reviews_count: int,
        success: bool = True,
        error_message: str = None,
        filter_type: str = None,
        questions_count: int = 0,
        avg_rating: float = 0,
        reviews_file_id: str = None,
        questions_file_id: str = None
    ):
        """Добавляет запрос в историю и обновляет счётчик пользователя"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO requests (
                user_id, marketplace, product_url, reviews_count, success, error_message,
                filter_type, questions_count, avg_rating, reviews_file_id, questions_file_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, marketplace, product_url, reviews_count, 1 if success else 0,
              error_message, filter_type, questions_count, avg_rating,
              reviews_file_id, questions_file_id))

        cursor.execute('''
            UPDATE users SET total_requests = total_requests + 1 WHERE user_id = ?
        ''', (user_id,))

        conn.commit()
        conn.close()

    def check_rate_limit(self, user_id: int, max_requests: int, hours: int) -> tuple:
        """
        Проверяет, не превысил ли пользователь лимит запросов.
        Возвращает (can_request: bool, remaining: int)
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        time_threshold = datetime.now() - timedelta(hours=hours)

        cursor.execute('''
            SELECT COUNT(*) FROM rate_limits
            WHERE user_id = ? AND created_at > ?
        ''', (user_id, time_threshold))

        count = cursor.fetchone()[0]
        conn.close()

        remaining = max_requests - count
        can_request = remaining > 0

        return can_request, remaining

    def add_rate_limit_record(self, user_id: int):
        """Добавляет запись о запросе для rate limiting"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO rate_limits (user_id) VALUES (?)
        ''', (user_id,))

        conn.commit()
        conn.close()

    def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        """Получает статистику пользователя"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT total_requests, first_seen, last_activity
            FROM users WHERE user_id = ?
        ''', (user_id,))

        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                'total_requests': row[0],
                'first_seen': row[1],
                'last_activity': row[2]
            }
        return {
            'total_requests': 0,
            'first_seen': None,
            'last_activity': None
        }

    def get_recent_requests(self, user_id: int, limit: int = 5) -> List[Dict]:
        """Получает последние запросы пользователя"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT id, marketplace, product_url, reviews_count, created_at, success,
                   filter_type, questions_count, avg_rating,
                   reviews_file_id, questions_file_id
            FROM requests
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        ''', (user_id, limit))

        rows = cursor.fetchall()
        conn.close()

        return [
            {
                'id': row[0],
                'marketplace': row[1],
                'product_url': row[2],
                'reviews_count': row[3],
                'created_at': row[4],
                'success': bool(row[5]),
                'filter_type': row[6],
                'questions_count': row[7],
                'avg_rating': row[8],
                'reviews_file_id': row[9],
                'questions_file_id': row[10],
            }
            for row in rows
        ]

    def get_total_stats(self) -> Dict[str, int]:
        """Получает общую статистику бота (для админов)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Всего пользователей
        cursor.execute('SELECT COUNT(*) FROM users')
        total_users = cursor.fetchone()[0]

        # Всего запросов
        cursor.execute('SELECT COUNT(*) FROM requests')
        total_requests = cursor.fetchone()[0]

        # Успешных запросов
        cursor.execute('SELECT COUNT(*) FROM requests WHERE success = 1')
        successful_requests = cursor.fetchone()[0]

        # Всего собрано отзывов
        cursor.execute('SELECT COALESCE(SUM(reviews_count), 0) FROM requests WHERE success = 1')
        total_reviews = cursor.fetchone()[0]

        conn.close()

        return {
            'total_users': total_users,
            'total_requests': total_requests,
            'successful_requests': successful_requests,
            'total_reviews': total_reviews
        }

    def get_all_user_ids(self) -> List[int]:
        """Возвращает список всех user_id (для рассылки)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM users')
        rows = cursor.fetchall()
        conn.close()
        return [row[0] for row in rows]

    def cleanup_old_rate_limits(self, hours: int = 24):
        """Удаляет старые записи rate limit"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        time_threshold = datetime.now() - timedelta(hours=hours)

        cursor.execute('''
            DELETE FROM rate_limits WHERE created_at < ?
        ''', (time_threshold,))

        conn.commit()
        conn.close()
