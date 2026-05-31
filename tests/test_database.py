"""
Unit-тесты для Database
"""

import pytest
import os
import tempfile
from database import Database


class TestDatabase:
    """Тесты для класса Database"""

    @pytest.fixture
    def temp_db(self):
        """Фикстура для временной базы данных"""
        # Создаем временный файл
        fd, db_path = tempfile.mkstemp(suffix='.db')
        os.close(fd)

        # Создаем экземпляр базы
        db = Database(db_path)

        yield db

        # Очищаем после теста
        if os.path.exists(db_path):
            os.remove(db_path)

    def test_create_tables(self, temp_db):
        """Тест создания таблиц"""
        # Таблицы должны быть созданы в __init__
        cursor = temp_db.conn.cursor()

        # Проверяем наличие таблицы users
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        assert cursor.fetchone() is not None

        # Проверяем наличие таблицы requests
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='requests'")
        assert cursor.fetchone() is not None

        # Проверяем наличие таблицы rate_limits
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='rate_limits'")
        assert cursor.fetchone() is not None

    def test_add_user_new(self, temp_db):
        """Тест добавления нового пользователя"""
        user_id = 12345
        username = "testuser"

        temp_db.add_user(user_id, username)

        # Проверяем что пользователь добавлен
        cursor = temp_db.conn.cursor()
        cursor.execute("SELECT user_id, username FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()

        assert result is not None
        assert result[0] == user_id
        assert result[1] == username

    def test_add_user_existing(self, temp_db):
        """Тест добавления существующего пользователя"""
        user_id = 12345
        username1 = "testuser1"
        username2 = "testuser2"

        # Добавляем пользователя первый раз
        temp_db.add_user(user_id, username1)

        # Добавляем того же пользователя с другим username
        temp_db.add_user(user_id, username2)

        # Должен быть только один пользователь
        cursor = temp_db.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE user_id = ?", (user_id,))
        count = cursor.fetchone()[0]
        assert count == 1

    def test_log_request(self, temp_db):
        """Тест логирования запроса"""
        user_id = 12345
        marketplace = "wildberries"
        product_url = "https://wildberries.ru/catalog/123/detail"
        reviews_count = 50
        success = True

        temp_db.log_request(user_id, marketplace, product_url, reviews_count, success)

        # Проверяем что запрос залогирован
        cursor = temp_db.conn.cursor()
        cursor.execute("""
            SELECT user_id, marketplace, product_url, reviews_count, success
            FROM requests
            WHERE user_id = ?
        """, (user_id,))
        result = cursor.fetchone()

        assert result is not None
        assert result[0] == user_id
        assert result[1] == marketplace
        assert result[2] == product_url
        assert result[3] == reviews_count
        assert result[4] == success

    def test_check_rate_limit_no_limit(self, temp_db):
        """Тест проверки rate limit когда лимит не превышен"""
        user_id = 12345

        can_proceed, remaining = temp_db.check_rate_limit(user_id, limit=5, hours=1)

        assert can_proceed is True
        assert remaining == 5

    def test_check_rate_limit_exceeded(self, temp_db):
        """Тест проверки rate limit когда лимит превышен"""
        user_id = 12345
        marketplace = "wildberries"
        url = "https://wildberries.ru/catalog/123/detail"

        # Добавляем 5 запросов
        for i in range(5):
            temp_db.log_request(user_id, marketplace, f"{url}?id={i}", 10, True)

        # Проверяем лимит (должен быть превышен)
        can_proceed, remaining = temp_db.check_rate_limit(user_id, limit=5, hours=1)

        assert can_proceed is False
        assert remaining == 0

    def test_get_user_stats_new_user(self, temp_db):
        """Тест получения статистики нового пользователя"""
        user_id = 99999

        stats = temp_db.get_user_stats(user_id)

        assert stats["total_requests"] == 0
        assert stats["successful_requests"] == 0
        assert stats["failed_requests"] == 0
        assert stats["total_reviews"] == 0

    def test_get_user_stats_with_requests(self, temp_db):
        """Тест получения статистики пользователя с запросами"""
        user_id = 12345
        marketplace = "wildberries"
        url = "https://wildberries.ru/catalog/123/detail"

        # Добавляем успешные и неуспешные запросы
        temp_db.log_request(user_id, marketplace, url, 10, True)
        temp_db.log_request(user_id, marketplace, url, 20, True)
        temp_db.log_request(user_id, marketplace, url, 0, False)

        stats = temp_db.get_user_stats(user_id)

        assert stats["total_requests"] == 3
        assert stats["successful_requests"] == 2
        assert stats["failed_requests"] == 1
        assert stats["total_reviews"] == 30  # 10 + 20

    def test_get_all_users(self, temp_db):
        """Тест получения всех пользователей"""
        # Добавляем несколько пользователей
        temp_db.add_user(111, "user1")
        temp_db.add_user(222, "user2")
        temp_db.add_user(333, "user3")

        users = temp_db.get_all_users()

        assert len(users) == 3
        user_ids = [user[0] for user in users]
        assert 111 in user_ids
        assert 222 in user_ids
        assert 333 in user_ids

    def test_get_bot_stats(self, temp_db):
        """Тест получения общей статистики бота"""
        # Добавляем пользователей и запросы
        temp_db.add_user(111, "user1")
        temp_db.add_user(222, "user2")

        temp_db.log_request(111, "wildberries", "url1", 10, True)
        temp_db.log_request(222, "ozon", "url2", 20, True)
        temp_db.log_request(111, "wildberries", "url3", 0, False)

        stats = temp_db.get_bot_stats()

        assert stats["total_users"] == 2
        assert stats["total_requests"] == 3
        assert stats["total_reviews_parsed"] == 30  # 10 + 20

    def test_database_persistence(self):
        """Тест персистентности данных"""
        # Создаем временный файл
        fd, db_path = tempfile.mkstemp(suffix='.db')
        os.close(fd)

        try:
            # Создаем первую сессию и добавляем данные
            db1 = Database(db_path)
            db1.add_user(12345, "testuser")
            db1.log_request(12345, "wildberries", "url", 10, True)
            db1.close()

            # Создаем вторую сессию и проверяем данные
            db2 = Database(db_path)
            stats = db2.get_user_stats(12345)

            assert stats["total_requests"] == 1
            assert stats["total_reviews"] == 10

            db2.close()
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)

    def test_concurrent_writes(self, temp_db):
        """Тест одновременных записей"""
        user_id = 12345

        # Добавляем несколько запросов подряд
        for i in range(10):
            temp_db.log_request(user_id, "wildberries", f"url_{i}", i, True)

        # Проверяем что все записаны
        cursor = temp_db.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM requests WHERE user_id = ?", (user_id,))
        count = cursor.fetchone()[0]

        assert count == 10

    def test_close_database(self, temp_db):
        """Тест закрытия соединения с БД"""
        temp_db.close()

        # После закрытия не должны работать запросы
        with pytest.raises(Exception):
            temp_db.add_user(12345, "testuser")

    def test_sql_injection_protection(self, temp_db):
        """Тест защиты от SQL injection"""
        malicious_username = "'; DROP TABLE users; --"
        user_id = 12345

        # Попытка SQL injection через username
        temp_db.add_user(user_id, malicious_username)

        # Проверяем что таблица users все еще существует
        cursor = temp_db.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        assert cursor.fetchone() is not None

        # И пользователь добавлен корректно
        cursor.execute("SELECT username FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        assert result[0] == malicious_username

    def test_add_request_stores_new_fields(self, temp_db):
        """Тест что add_request сохраняет новые поля"""
        temp_db.add_or_update_user(1, "u", "f", "l")
        temp_db.add_request(
            user_id=1, marketplace="Wildberries",
            product_url="https://www.wildberries.ru/catalog/12345678/detail.aspx",
            reviews_count=33, success=True,
            filter_type="1-3", questions_count=32, avg_rating=2.1,
            reviews_file_id="REV_FILE_ID", questions_file_id="Q_FILE_ID",
        )
        rows = temp_db.get_recent_requests(1, limit=5)
        assert len(rows) == 1
        r = rows[0]
        assert r['filter_type'] == "1-3"
        assert r['questions_count'] == 32
        assert r['avg_rating'] == 2.1
        assert r['reviews_file_id'] == "REV_FILE_ID"
        assert r['questions_file_id'] == "Q_FILE_ID"
        assert 'id' in r

    def test_add_request_backward_compatible(self, temp_db):
        """Тест обратной совместимости add_request без новых полей"""
        temp_db.add_or_update_user(2, "u", "f", "l")
        temp_db.add_request(2, "Wildberries", "https://x", 0, success=False,
                            error_message="нет данных")
        rows = temp_db.get_recent_requests(2, limit=5)
        assert rows[0]['success'] is False
        assert rows[0]['filter_type'] is None
        assert rows[0]['questions_count'] == 0
        assert rows[0]['reviews_file_id'] is None


def test_init_database_migrates_old_schema(tmp_path):
    """Тест что init_database мигрирует старую схему без новых колонок"""
    import sqlite3
    from database import Database
    db_file = str(tmp_path / "old.db")
    # старая схема requests без новых колонок
    conn = sqlite3.connect(db_file)
    conn.execute('''CREATE TABLE requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, marketplace TEXT, product_url TEXT,
        reviews_count INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        success INTEGER DEFAULT 1, error_message TEXT)''')
    conn.execute('''CREATE TABLE users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        last_name TEXT,
        first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        total_requests INTEGER DEFAULT 0)''')
    conn.execute('''CREATE TABLE rate_limits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

    db = Database(db_path=db_file)
    db.init_database()  # должна добавить недостающие колонки без ошибок
    db.add_or_update_user(1, "u", "f", "l")
    db.add_request(1, "Wildberries", "https://x", 5, success=True,
                   filter_type="4-5", questions_count=3, avg_rating=4.5,
                   reviews_file_id="RID", questions_file_id="QID")
    rows = db.get_recent_requests(1, limit=5)
    assert rows[0]['filter_type'] == "4-5"
    assert rows[0]['reviews_file_id'] == "RID"
