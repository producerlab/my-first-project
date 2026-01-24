"""
Unit-тесты для SentimentAnalyzer
"""

import pytest
from sentiment_analyzer import SentimentAnalyzer


class TestSentimentAnalyzer:
    """Тесты анализатора тональности"""

    @pytest.fixture
    def analyzer(self):
        """Фикстура с экземпляром анализатора"""
        return SentimentAnalyzer()

    def test_analyze_positive_review(self, analyzer):
        """Тест анализа позитивного отзыва"""
        review = "Отличный товар! Очень доволен покупкой. Рекомендую всем!"
        sentiment = analyzer.analyze_sentiment(review)
        assert sentiment == "Позитивный"

    def test_analyze_negative_review(self, analyzer):
        """Тест анализа негативного отзыва"""
        review = "Ужасное качество! Разочарован. Не рекомендую никому. Брак и обман!"
        sentiment = analyzer.analyze_sentiment(review)
        assert sentiment == "Негативный"

    def test_analyze_neutral_review(self, analyzer):
        """Тест анализа нейтрального отзыва"""
        review = "Обычный товар. Ничего особенного."
        sentiment = analyzer.analyze_sentiment(review)
        assert sentiment == "Нейтральный"

    def test_analyze_empty_review(self, analyzer):
        """Тест анализа пустого отзыва"""
        sentiment = analyzer.analyze_sentiment("")
        assert sentiment == "Нейтральный"

    def test_analyze_mixed_review(self, analyzer):
        """Тест анализа смешанного отзыва (больше позитива)"""
        review = "Товар хороший, но есть небольшие недостатки. В целом доволен."
        sentiment = analyzer.analyze_sentiment(review)
        # Должен быть либо позитивный, либо нейтральный
        assert sentiment in ["Позитивный", "Нейтральный"]

    def test_detect_problem_review(self, analyzer):
        """Тест определения отзыва с проблемой"""
        review = "Товар бракованный, не работает!"
        has_problem = analyzer.has_problem(review)
        assert has_problem is True

    def test_detect_no_problem_review(self, analyzer):
        """Тест определения отзыва без проблемы"""
        review = "Отличный товар, все работает!"
        has_problem = analyzer.has_problem(review)
        assert has_problem is False

    def test_extract_key_phrases(self, analyzer):
        """Тест извлечения ключевых фраз"""
        reviews = [
            {"text": "Отличное качество товара"},
            {"text": "Хорошая цена и быстрая доставка"},
            {"text": "Качество супер"}
        ]
        key_phrases = analyzer.extract_key_phrases(reviews, top_n=2)
        assert len(key_phrases) <= 2
        assert all(isinstance(phrase, tuple) for phrase in key_phrases)
        assert all(len(phrase) == 2 for phrase in key_phrases)  # (phrase, count)

    def test_extract_key_phrases_empty(self, analyzer):
        """Тест извлечения ключевых фраз из пустого списка"""
        key_phrases = analyzer.extract_key_phrases([], top_n=5)
        assert len(key_phrases) == 0

    def test_analyze_reviews_batch(self, analyzer):
        """Тест пакетного анализа отзывов"""
        reviews = [
            {"text": "Отлично", "rating": 5},
            {"text": "Плохо", "rating": 1},
            {"text": "Нормально", "rating": 3}
        ]

        results = analyzer.analyze_reviews(reviews)

        assert "total" in results
        assert "positive" in results
        assert "negative" in results
        assert "neutral" in results
        assert results["total"] == 3
        assert results["positive"] + results["negative"] + results["neutral"] == 3

    def test_case_insensitivity(self, analyzer):
        """Тест нечувствительности к регистру"""
        review_lower = "отличный товар"
        review_upper = "ОТЛИЧНЫЙ ТОВАР"
        review_mixed = "ОтЛиЧнЫй ТоВаР"

        sentiment_lower = analyzer.analyze_sentiment(review_lower)
        sentiment_upper = analyzer.analyze_sentiment(review_upper)
        sentiment_mixed = analyzer.analyze_sentiment(review_mixed)

        assert sentiment_lower == sentiment_upper == sentiment_mixed == "Позитивный"

    def test_punctuation_handling(self, analyzer):
        """Тест обработки пунктуации"""
        review_with_punct = "Отличный!!! товар??? Супер..."
        review_without_punct = "Отличный товар Супер"

        sentiment_with = analyzer.analyze_sentiment(review_with_punct)
        sentiment_without = analyzer.analyze_sentiment(review_without_punct)

        assert sentiment_with == sentiment_without == "Позитивный"

    def test_very_short_review(self, analyzer):
        """Тест очень короткого отзыва"""
        sentiment = analyzer.analyze_sentiment("Супер")
        assert sentiment == "Позитивный"

    def test_very_long_review(self, analyzer):
        """Тест очень длинного отзыва"""
        review = "Отличный " * 100 + "товар!"
        sentiment = analyzer.analyze_sentiment(review)
        assert sentiment == "Позитивный"

    def test_rating_correlation(self, analyzer):
        """Тест корреляции с рейтингом"""
        reviews_5_star = [
            {"text": "Отлично", "rating": 5},
            {"text": "Супер", "rating": 5}
        ]
        reviews_1_star = [
            {"text": "Ужасно", "rating": 1},
            {"text": "Плохо", "rating": 1}
        ]

        results_5 = analyzer.analyze_reviews(reviews_5_star)
        results_1 = analyzer.analyze_reviews(reviews_1_star)

        # У 5-звездочных больше позитива
        assert results_5["positive"] > results_5["negative"]
        # У 1-звездочных больше негатива
        assert results_1["negative"] > results_1["positive"]
