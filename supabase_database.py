"""
Реализация базы данных на Supabase.
Имеет тот же интерфейс что и Database (SQLite), для бесшовной замены.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from supabase import create_client, Client
from config import Config

logger = logging.getLogger(__name__)


class SupabaseDatabase:
    """Работа с Supabase базой данных для парсера отзывов WB"""

    def __init__(self):
        if not Config.use_supabase():
            raise ValueError("Supabase не настроен. Проверьте SUPABASE_URL и SUPABASE_KEY")

        self.client: Client = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
        logger.info("Подключение к Supabase установлено")

    def add_or_update_user(
        self,
        user_id: int,
        username: str = None,
        first_name: str = None,
        last_name: str = None
    ):
        """Добавляет нового пользователя или обновляет существующего"""
        try:
            # Проверяем существует ли пользователь
            result = self.client.table('users').select('user_id').eq('user_id', user_id).execute()

            now = datetime.now().isoformat()

            if result.data:
                # Обновляем существующего
                update_data = {'last_activity': now}
                if username:
                    update_data['username'] = username
                if first_name:
                    update_data['first_name'] = first_name
                if last_name:
                    update_data['last_name'] = last_name

                self.client.table('users').update(update_data).eq('user_id', user_id).execute()
            else:
                # Создаём нового
                self.client.table('users').insert({
                    'user_id': user_id,
                    'username': username,
                    'first_name': first_name,
                    'last_name': last_name,
                    'first_seen': now,
                    'last_activity': now,
                    'total_requests': 0
                }).execute()

        except Exception as e:
            logger.error(f"Ошибка Supabase add_or_update_user: {e}")

    def add_request(
        self,
        user_id: int,
        marketplace: str,
        product_url: str,
        reviews_count: int,
        success: bool = True,
        error_message: str = None
    ):
        """Добавляет запрос в историю и обновляет счётчик пользователя"""
        try:
            # Добавляем запрос
            self.client.table('requests').insert({
                'user_id': user_id,
                'marketplace': marketplace,
                'product_url': product_url,
                'reviews_count': reviews_count,
                'success': success,
                'error_message': error_message,
                'created_at': datetime.now().isoformat()
            }).execute()

            # Обновляем счётчик пользователя
            result = self.client.table('users').select('total_requests').eq('user_id', user_id).execute()
            if result.data:
                current = result.data[0].get('total_requests', 0) or 0
                self.client.table('users').update({
                    'total_requests': current + 1
                }).eq('user_id', user_id).execute()

        except Exception as e:
            logger.error(f"Ошибка Supabase add_request: {e}")

    def check_rate_limit(self, user_id: int, max_requests: int, hours: int) -> tuple:
        """
        Проверяет, не превысил ли пользователь лимит запросов.
        Возвращает (can_request: bool, remaining: int)
        """
        try:
            time_threshold = (datetime.now() - timedelta(hours=hours)).isoformat()

            result = self.client.table('rate_limits')\
                .select('id', count='exact')\
                .eq('user_id', user_id)\
                .gte('created_at', time_threshold)\
                .execute()

            count = result.count or 0
            remaining = max_requests - count
            can_request = remaining > 0

            return can_request, remaining

        except Exception as e:
            logger.error(f"Ошибка Supabase check_rate_limit: {e}")
            return True, max_requests  # В случае ошибки разрешаем запрос

    def add_rate_limit_record(self, user_id: int):
        """Добавляет запись о запросе для rate limiting"""
        try:
            self.client.table('rate_limits').insert({
                'user_id': user_id,
                'created_at': datetime.now().isoformat()
            }).execute()
        except Exception as e:
            logger.error(f"Ошибка Supabase add_rate_limit_record: {e}")

    def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        """Получает статистику пользователя"""
        try:
            result = self.client.table('users')\
                .select('total_requests, first_seen, last_activity')\
                .eq('user_id', user_id)\
                .execute()

            if result.data:
                row = result.data[0]
                return {
                    'total_requests': row.get('total_requests', 0),
                    'first_seen': row.get('first_seen'),
                    'last_activity': row.get('last_activity')
                }
        except Exception as e:
            logger.error(f"Ошибка Supabase get_user_stats: {e}")

        return {
            'total_requests': 0,
            'first_seen': None,
            'last_activity': None
        }

    def get_recent_requests(self, user_id: int, limit: int = 5) -> List[Dict]:
        """Получает последние запросы пользователя"""
        try:
            result = self.client.table('requests')\
                .select('marketplace, product_url, reviews_count, created_at, success')\
                .eq('user_id', user_id)\
                .order('created_at', desc=True)\
                .limit(limit)\
                .execute()

            return [
                {
                    'marketplace': row.get('marketplace'),
                    'product_url': row.get('product_url'),
                    'reviews_count': row.get('reviews_count'),
                    'created_at': row.get('created_at'),
                    'success': row.get('success', True)
                }
                for row in result.data
            ]
        except Exception as e:
            logger.error(f"Ошибка Supabase get_recent_requests: {e}")
            return []

    def get_total_stats(self) -> Dict[str, int]:
        """Получает общую статистику бота (для админов)"""
        try:
            # Всего пользователей
            users_result = self.client.table('users').select('user_id', count='exact').execute()
            total_users = users_result.count or 0

            # Всего запросов
            requests_result = self.client.table('requests').select('id', count='exact').execute()
            total_requests = requests_result.count or 0

            # Успешных запросов
            success_result = self.client.table('requests')\
                .select('id', count='exact')\
                .eq('success', True)\
                .execute()
            successful_requests = success_result.count or 0

            # Всего собрано отзывов
            reviews_result = self.client.table('requests')\
                .select('reviews_count')\
                .eq('success', True)\
                .execute()
            total_reviews = sum(r.get('reviews_count', 0) or 0 for r in reviews_result.data)

            return {
                'total_users': total_users,
                'total_requests': total_requests,
                'successful_requests': successful_requests,
                'total_reviews': total_reviews
            }
        except Exception as e:
            logger.error(f"Ошибка Supabase get_total_stats: {e}")
            return {
                'total_users': 0,
                'total_requests': 0,
                'successful_requests': 0,
                'total_reviews': 0
            }

    def cleanup_old_rate_limits(self, hours: int = 24):
        """Удаляет старые записи rate limit"""
        try:
            time_threshold = (datetime.now() - timedelta(hours=hours)).isoformat()

            self.client.table('rate_limits')\
                .delete()\
                .lt('created_at', time_threshold)\
                .execute()

            logger.info(f"Очищены rate_limits старше {hours} часов")
        except Exception as e:
            logger.error(f"Ошибка Supabase cleanup_old_rate_limits: {e}")
