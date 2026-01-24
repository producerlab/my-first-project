"""
Централизованная конфигурация приложения.
Все настройки загружаются из переменных окружения (.env файл).
"""

import os
from typing import List
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()


class Config:
    """Класс конфигурации приложения"""

    # Telegram Bot настройки
    BOT_TOKEN: str = os.getenv('BOT_TOKEN', '')

    # Администраторы бота (список Telegram ID через запятую)
    ADMIN_IDS: List[int] = [
        int(admin_id.strip())
        for admin_id in os.getenv('ADMIN_IDS', '').split(',')
        if admin_id.strip()
    ]

    # Rate Limiting настройки
    RATE_LIMIT_REQUESTS: int = int(os.getenv('RATE_LIMIT_REQUESTS', '5'))
    RATE_LIMIT_HOURS: int = int(os.getenv('RATE_LIMIT_HOURS', '1'))

    # Ограничения парсинга
    MAX_REVIEWS: int = int(os.getenv('MAX_REVIEWS', '1000'))
    MAX_QUESTIONS: int = int(os.getenv('MAX_QUESTIONS', '1000'))

    # Канал для проверки подписки
    REQUIRED_CHANNEL: str = os.getenv('REQUIRED_CHANNEL', '@khosnullin_channel')

    # Парсер настройки
    PARSER_TIMEOUT: int = int(os.getenv('PARSER_TIMEOUT', '60000'))
    PARSER_HEADLESS: bool = os.getenv('PARSER_HEADLESS', 'True').lower() == 'true'

    # Retry настройки
    RETRY_MAX_ATTEMPTS: int = int(os.getenv('RETRY_MAX_ATTEMPTS', '3'))
    RETRY_MIN_WAIT: int = int(os.getenv('RETRY_MIN_WAIT', '2'))
    RETRY_MAX_WAIT: int = int(os.getenv('RETRY_MAX_WAIT', '10'))

    # Supabase настройки (опционально, если не указано - используется SQLite)
    SUPABASE_URL: str = os.getenv('SUPABASE_URL', '')
    SUPABASE_KEY: str = os.getenv('SUPABASE_KEY', '')

    @classmethod
    def use_supabase(cls) -> bool:
        """Проверяет, настроен ли Supabase"""
        return bool(cls.SUPABASE_URL and cls.SUPABASE_KEY)

    @classmethod
    def validate(cls) -> None:
        """Валидация конфигурации"""
        if not cls.BOT_TOKEN:
            raise ValueError("BOT_TOKEN не задан в .env файле")

        if cls.MAX_REVIEWS <= 0 or cls.MAX_REVIEWS > 5000:
            raise ValueError("MAX_REVIEWS должен быть в диапазоне 1-5000")


# Валидируем конфигурацию при импорте
try:
    Config.validate()
except ValueError as e:
    print(f"ОШИБКА КОНФИГУРАЦИИ: {e}")
    print("Пожалуйста, проверьте .env файл")
    exit(1)
