"""
Unit-тесты для URLValidator
"""

import pytest
from url_validator import URLValidator, validate_url, get_marketplace_from_url
from exceptions import InvalidURLError


class TestURLValidator:
    """Тесты валидатора URL"""

    # === Тесты Wildberries URL ===

    def test_valid_wb_url(self):
        """Тест валидного URL Wildberries"""
        url = "https://www.wildberries.ru/catalog/12345678/detail.aspx"
        marketplace, product_id = URLValidator.validate_url(url)
        assert marketplace == "wildberries"
        assert product_id == "12345678"

    def test_valid_wb_short_domain(self):
        """Тест валидного короткого домена WB"""
        url = "https://wb.ru/catalog/98765432/detail.aspx"
        marketplace, product_id = URLValidator.validate_url(url)
        assert marketplace == "wildberries"
        assert product_id == "98765432"

    def test_valid_wb_without_www(self):
        """Тест валидного URL WB без www"""
        url = "https://wildberries.ru/catalog/11111111/detail.aspx"
        marketplace, product_id = URLValidator.validate_url(url)
        assert marketplace == "wildberries"
        assert product_id == "11111111"

    # === Тесты Ozon URL ===

    def test_valid_ozon_url(self):
        """Тест валидного URL Ozon"""
        url = "https://www.ozon.ru/product/some-product-name-123456789"
        marketplace, product_id = URLValidator.validate_url(url)
        assert marketplace == "ozon"
        assert product_id == "123456789"

    def test_valid_ozon_without_www(self):
        """Тест валидного URL Ozon без www"""
        url = "https://ozon.ru/product/another-product-987654321"
        marketplace, product_id = URLValidator.validate_url(url)
        assert marketplace == "ozon"
        assert product_id == "987654321"

    # === Тесты невалидных URL ===

    def test_empty_url(self):
        """Тест пустого URL"""
        with pytest.raises(InvalidURLError) as exc_info:
            URLValidator.validate_url("")
        assert "не может быть пустым" in str(exc_info.value)

    def test_url_without_protocol(self):
        """Тест URL без протокола"""
        url = "wildberries.ru/catalog/12345678/detail"
        with pytest.raises(InvalidURLError) as exc_info:
            URLValidator.validate_url(url)
        assert "http://" in str(exc_info.value) or "https://" in str(exc_info.value)

    def test_unsupported_domain(self):
        """Тест неподдерживаемого домена"""
        url = "https://amazon.com/product/123"
        with pytest.raises(InvalidURLError) as exc_info:
            URLValidator.validate_url(url)
        assert "Неподдерживаемый домен" in str(exc_info.value)

    def test_url_without_product_id(self):
        """Тест URL без ID товара"""
        url = "https://wildberries.ru/"
        with pytest.raises(InvalidURLError) as exc_info:
            URLValidator.validate_url(url)
        assert "ID товара" in str(exc_info.value)

    def test_malformed_url(self):
        """Тест некорректного URL"""
        url = "https://wildberries.ru/ /catalog/invalid"
        with pytest.raises(InvalidURLError):
            URLValidator.validate_url(url)

    # === Тесты sanitize_url ===

    def test_sanitize_url_with_spaces(self):
        """Тест очистки URL с пробелами"""
        url = "  https://wildberries.ru/catalog/123/detail  "
        cleaned = URLValidator.sanitize_url(url)
        assert cleaned == "https://wildberries.ru/catalog/123/detail"

    def test_sanitize_url_javascript_protocol(self):
        """Тест защиты от javascript: протокола"""
        url = "javascript:alert('xss')"
        with pytest.raises(InvalidURLError) as exc_info:
            URLValidator.sanitize_url(url)
        assert "Недопустимый протокол" in str(exc_info.value)

    def test_sanitize_url_data_protocol(self):
        """Тест защиты от data: протокола"""
        url = "data:text/html,<script>alert('xss')</script>"
        with pytest.raises(InvalidURLError) as exc_info:
            URLValidator.sanitize_url(url)
        assert "Недопустимый протокол" in str(exc_info.value)

    def test_sanitize_url_too_long(self):
        """Тест защиты от слишком длинного URL"""
        url = "https://wildberries.ru/" + "a" * 3000
        with pytest.raises(InvalidURLError) as exc_info:
            URLValidator.sanitize_url(url)
        assert "слишком длинный" in str(exc_info.value)

    # === Тесты вспомогательных функций ===

    def test_is_valid_wildberries_url_true(self):
        """Тест проверки валидного WB URL"""
        url = "https://wildberries.ru/catalog/123/detail"
        assert URLValidator.is_valid_wildberries_url(url) is True

    def test_is_valid_wildberries_url_false(self):
        """Тест проверки невалидного WB URL"""
        url = "https://ozon.ru/product/test-123"
        assert URLValidator.is_valid_wildberries_url(url) is False

    def test_is_valid_ozon_url_true(self):
        """Тест проверки валидного Ozon URL"""
        url = "https://ozon.ru/product/test-123"
        assert URLValidator.is_valid_ozon_url(url) is True

    def test_is_valid_ozon_url_false(self):
        """Тест проверки невалидного Ozon URL"""
        url = "https://wildberries.ru/catalog/123/detail"
        assert URLValidator.is_valid_ozon_url(url) is False

    # === Тесты глобальных функций ===

    def test_validate_url_function(self):
        """Тест глобальной функции validate_url"""
        url = "  https://wildberries.ru/catalog/123/detail  "
        marketplace, product_id = validate_url(url)
        assert marketplace == "wildberries"
        assert product_id == "123"

    def test_get_marketplace_from_url_wb(self):
        """Тест определения маркетплейса WB"""
        url = "https://wildberries.ru/catalog/123/detail"
        marketplace = get_marketplace_from_url(url)
        assert marketplace == "wildberries"

    def test_get_marketplace_from_url_ozon(self):
        """Тест определения маркетплейса Ozon"""
        url = "https://ozon.ru/product/test-123"
        marketplace = get_marketplace_from_url(url)
        assert marketplace == "ozon"

    def test_get_marketplace_from_url_invalid(self):
        """Тест определения маркетплейса для невалидного URL"""
        url = "https://invalid.com/product/123"
        marketplace = get_marketplace_from_url(url)
        assert marketplace is None

    # === Тесты edge cases ===

    def test_url_with_query_params(self):
        """Тест URL с query параметрами"""
        url = "https://wildberries.ru/catalog/123/detail?param=value&other=123"
        marketplace, product_id = URLValidator.validate_url(url)
        assert marketplace == "wildberries"
        assert product_id == "123"

    def test_url_with_hash(self):
        """Тест URL с hash (#)"""
        url = "https://wildberries.ru/catalog/123/detail#section"
        marketplace, product_id = URLValidator.validate_url(url)
        assert marketplace == "wildberries"
        assert product_id == "123"

    def test_http_protocol(self):
        """Тест HTTP протокола (не только HTTPS)"""
        url = "http://wildberries.ru/catalog/123/detail"
        marketplace, product_id = URLValidator.validate_url(url)
        assert marketplace == "wildberries"
        assert product_id == "123"

    def test_case_insensitive_domain(self):
        """Тест нечувствительности к регистру домена"""
        url = "https://WILDBERRIES.RU/catalog/123/detail"
        marketplace, product_id = URLValidator.validate_url(url)
        assert marketplace == "wildberries"
        assert product_id == "123"
