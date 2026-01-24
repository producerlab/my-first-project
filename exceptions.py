"""
Custom исключения для парсеров и бота.
Позволяют более точно обрабатывать различные типы ошибок.
"""


class ParserError(Exception):
    """Базовое исключение для всех ошибок парсеров"""
    pass


class NetworkError(ParserError):
    """Ошибка сетевого соединения"""
    def __init__(self, message: str = "Ошибка сетевого подключения", url: str = None):
        self.url = url
        super().__init__(f"{message}{f' ({url})' if url else ''}")


class InvalidURLError(ParserError):
    """Невалидный или неподдерживаемый URL"""
    def __init__(self, url: str, reason: str = None):
        self.url = url
        self.reason = reason
        message = f"Невалидный URL: {url}"
        if reason:
            message += f" - {reason}"
        super().__init__(message)


class NoDataFoundError(ParserError):
    """Не найдено отзывов или вопросов на странице"""
    def __init__(self, data_type: str = "данные", url: str = None):
        self.data_type = data_type
        self.url = url
        message = f"Не найдено {data_type}"
        if url:
            message += f" по адресу {url}"
        super().__init__(message)


class PageLoadError(ParserError):
    """Ошибка загрузки страницы"""
    def __init__(self, message: str = "Не удалось загрузить страницу", url: str = None):
        self.url = url
        super().__init__(f"{message}{f': {url}' if url else ''}")


class TimeoutError(ParserError):
    """Превышен timeout ожидания"""
    def __init__(self, operation: str = "операция", timeout: int = None):
        self.operation = operation
        self.timeout = timeout
        message = f"Превышен timeout для операции: {operation}"
        if timeout:
            message += f" ({timeout}ms)"
        super().__init__(message)


class RateLimitError(ParserError):
    """Превышен rate limit маркетплейса (429 Too Many Requests)"""
    def __init__(self, marketplace: str = None, retry_after: int = None):
        self.marketplace = marketplace
        self.retry_after = retry_after
        message = "Превышен лимит запросов"
        if marketplace:
            message += f" на {marketplace}"
        if retry_after:
            message += f". Повторите попытку через {retry_after} секунд"
        super().__init__(message)


class APIResponseError(ParserError):
    """Ошибка в ответе API (неожиданная структура данных)"""
    def __init__(self, message: str = "Неожиданная структура ответа API", details: str = None):
        self.details = details
        full_message = message
        if details:
            full_message += f": {details}"
        super().__init__(full_message)


class BrowserError(ParserError):
    """Ошибка при работе с браузером (Playwright)"""
    def __init__(self, message: str = "Ошибка браузера", browser_type: str = None):
        self.browser_type = browser_type
        full_message = message
        if browser_type:
            full_message += f" ({browser_type})"
        super().__init__(full_message)


class CaptchaDetectedError(ParserError):
    """Обнаружена капча на странице"""
    def __init__(self, marketplace: str = None):
        self.marketplace = marketplace
        message = "Обнаружена капча"
        if marketplace:
            message += f" на {marketplace}"
        message += ". Попробуйте позже"
        super().__init__(message)


class DataExportError(Exception):
    """Ошибка при экспорте данных"""
    def __init__(self, format_type: str = "неизвестный", message: str = None):
        self.format_type = format_type
        full_message = f"Ошибка экспорта в формат {format_type}"
        if message:
            full_message += f": {message}"
        super().__init__(full_message)


class DatabaseError(Exception):
    """Ошибка при работе с базой данных"""
    def __init__(self, operation: str = None, message: str = None):
        self.operation = operation
        full_message = "Ошибка базы данных"
        if operation:
            full_message += f" при выполнении операции: {operation}"
        if message:
            full_message += f" - {message}"
        super().__init__(full_message)


class ConfigurationError(Exception):
    """Ошибка конфигурации приложения"""
    def __init__(self, parameter: str = None, message: str = None):
        self.parameter = parameter
        full_message = "Ошибка конфигурации"
        if parameter:
            full_message += f" параметра '{parameter}'"
        if message:
            full_message += f": {message}"
        super().__init__(full_message)
