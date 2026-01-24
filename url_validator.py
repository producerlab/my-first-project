"""
Валидация URL для поддерживаемых маркетплейсов.
Проверяет корректность и безопасность входящих URL.
"""

import re
from urllib.parse import urlparse, parse_qs
from typing import Tuple, Optional
from exceptions import InvalidURLError


class URLValidator:
    """Валидатор URL для маркетплейсов"""

    # Разрешенные домены
    ALLOWED_DOMAINS = {
        'wildberries': ['wildberries.ru', 'www.wildberries.ru', 'wb.ru', 'www.wb.ru'],
        'ozon': ['ozon.ru', 'www.ozon.ru'],
    }

    # Паттерны для извлечения ID товаров
    WB_PRODUCT_PATTERN = re.compile(r'/catalog/(\d+)/detail')
    OZON_PRODUCT_PATTERN = re.compile(r'/product/[^/]+-(\d+)')

    @classmethod
    def validate_url(cls, url: str) -> Tuple[str, str]:
        """
        Валидирует URL и определяет маркетплейс.

        Args:
            url: URL для проверки

        Returns:
            Tuple[str, str]: (marketplace, product_id)
                marketplace: 'wildberries' или 'ozon'
                product_id: ID товара

        Raises:
            InvalidURLError: Если URL невалидный или неподдерживаемый
        """
        if not url:
            raise InvalidURLError(url="", reason="URL не может быть пустым")

        # Проверка что это HTTP(S) URL
        if not url.startswith(('http://', 'https://')):
            raise InvalidURLError(url=url, reason="URL должен начинаться с http:// или https://")

        try:
            parsed = urlparse(url)
        except Exception as e:
            raise InvalidURLError(url=url, reason=f"Ошибка парсинга URL: {str(e)}")

        # Проверка наличия домена
        if not parsed.netloc:
            raise InvalidURLError(url=url, reason="Отсутствует домен в URL")

        # Определение маркетплейса
        marketplace = cls._detect_marketplace(parsed.netloc)
        if not marketplace:
            allowed = ', '.join([
                domain
                for domains in cls.ALLOWED_DOMAINS.values()
                for domain in domains
            ])
            raise InvalidURLError(
                url=url,
                reason=f"Неподдерживаемый домен. Разрешены: {allowed}"
            )

        # Извлечение и валидация ID товара
        product_id = cls._extract_product_id(url, marketplace, parsed)
        if not product_id:
            raise InvalidURLError(
                url=url,
                reason=f"Не удалось извлечь ID товара из URL {marketplace}"
            )

        return marketplace, product_id

    @classmethod
    def _detect_marketplace(cls, domain: str) -> Optional[str]:
        """
        Определяет маркетплейс по домену.

        Args:
            domain: Доменное имя

        Returns:
            Optional[str]: Название маркетплейса или None
        """
        domain_lower = domain.lower()

        for marketplace, domains in cls.ALLOWED_DOMAINS.items():
            if domain_lower in domains:
                return marketplace

        return None

    @classmethod
    def _extract_product_id(cls, url: str, marketplace: str, parsed) -> Optional[str]:
        """
        Извлекает ID товара из URL.

        Args:
            url: Полный URL
            marketplace: Название маркетплейса
            parsed: Распарсенный URL (urlparse результат)

        Returns:
            Optional[str]: ID товара или None
        """
        if marketplace == 'wildberries':
            # Попытка извлечь из пути
            match = cls.WB_PRODUCT_PATTERN.search(parsed.path)
            if match:
                return match.group(1)

            # Fallback: попытка извлечь из query параметров
            query_params = parse_qs(parsed.query)
            if 'id' in query_params:
                return query_params['id'][0]

        elif marketplace == 'ozon':
            # Попытка извлечь из пути
            match = cls.OZON_PRODUCT_PATTERN.search(parsed.path)
            if match:
                return match.group(1)

        return None

    @classmethod
    def sanitize_url(cls, url: str) -> str:
        """
        Очищает URL от потенциально опасных параметров.

        Args:
            url: URL для очистки

        Returns:
            str: Очищенный URL
        """
        # Удаление пробелов по краям
        url = url.strip()

        # Удаление опасных протоколов
        dangerous_protocols = ['javascript:', 'data:', 'file:', 'vbscript:']
        url_lower = url.lower()
        for protocol in dangerous_protocols:
            if url_lower.startswith(protocol):
                raise InvalidURLError(url=url, reason=f"Недопустимый протокол: {protocol}")

        # Ограничение длины URL
        if len(url) > 2048:
            raise InvalidURLError(url=url, reason="URL слишком длинный (макс. 2048 символов)")

        return url

    @classmethod
    def is_valid_wildberries_url(cls, url: str) -> bool:
        """
        Быстрая проверка что URL принадлежит Wildberries.

        Args:
            url: URL для проверки

        Returns:
            bool: True если URL от Wildberries
        """
        try:
            marketplace, _ = cls.validate_url(url)
            return marketplace == 'wildberries'
        except InvalidURLError:
            return False

    @classmethod
    def is_valid_ozon_url(cls, url: str) -> bool:
        """
        Быстрая проверка что URL принадлежит Ozon.

        Args:
            url: URL для проверки

        Returns:
            bool: True если URL от Ozon
        """
        try:
            marketplace, _ = cls.validate_url(url)
            return marketplace == 'ozon'
        except InvalidURLError:
            return False


# Удобные функции для быстрого использования
def validate_url(url: str) -> Tuple[str, str]:
    """
    Валидирует URL маркетплейса.

    Args:
        url: URL для проверки

    Returns:
        Tuple[str, str]: (marketplace, product_id)

    Raises:
        InvalidURLError: Если URL невалидный
    """
    url = URLValidator.sanitize_url(url)
    return URLValidator.validate_url(url)


def get_marketplace_from_url(url: str) -> Optional[str]:
    """
    Определяет маркетплейс из URL без исключений.

    Args:
        url: URL для проверки

    Returns:
        Optional[str]: Название маркетплейса или None
    """
    try:
        marketplace, _ = validate_url(url)
        return marketplace
    except InvalidURLError:
        return None
