"""
Анализатор тональности отзывов на русском языке
Использует словари ключевых слов для определения позитивных и негативных отзывов
"""

from typing import List, Dict
from collections import Counter
import re


class SentimentAnalyzer:
    """Анализатор тональности отзывов"""

    def __init__(self):
        # Позитивные слова
        self.positive_words = {
            'отлично', 'отличный', 'прекрасно', 'замечательно', 'супер', 'класс',
            'восторг', 'идеально', 'превосходно', 'шикарно', 'люблю', 'нравится',
            'рекомендую', 'советую', 'качественно', 'хорошо', 'хороший', 'удобно',
            'понравилось', 'довольна', 'доволен', 'радует', 'восхищена', 'лучший',
            'топ', 'огонь', 'бомба', 'круто', 'стоит', 'красиво', 'быстро',
            'вкусно', 'мягкий', 'удобный', 'качество', 'спасибо', 'благодарю',
            'ожидания', 'превзошло', 'отменно'
        }

        # Негативные слова
        self.negative_words = {
            'плохо', 'плохой', 'ужасно', 'ужасный', 'разочарован', 'разочарована',
            'не рекомендую', 'не советую', 'обман', 'брак', 'дефект', 'плохое',
            'качество плохое', 'не понравилось', 'не нравится', 'жаль', 'испортился',
            'сломался', 'развалился', 'не соответствует', 'обманули', 'вернул',
            'деньги', 'выброшенные', 'кошмар', 'катастрофа', 'слабый', 'хрупкий',
            'тонкий', 'мало', 'дорого', 'не стоит', 'переплата', 'запах', 'вонь',
            'грубый', 'маленький', 'большой', 'не подошло', 'не подошел'
        }

        # Слова для выделения проблем
        self.problem_keywords = {
            'брак', 'дефект', 'сломался', 'не работает', 'не включается',
            'не соответствует', 'маленький', 'большой', 'запах', 'пятна',
            'царапины', 'грязный', 'рваный', 'кривой', 'плохо упаковано'
        }

    def analyze_review(self, review_text: str, rating: int) -> Dict:
        """
        Анализирует один отзыв

        Args:
            review_text: текст отзыва
            rating: рейтинг (1-5)

        Returns:
            Dict с результатами анализа
        """
        text_lower = review_text.lower()

        # Подсчет позитивных и негативных слов
        positive_count = sum(1 for word in self.positive_words if word in text_lower)
        negative_count = sum(1 for word in self.negative_words if word in text_lower)

        # Определение тональности
        if rating >= 4 and positive_count > negative_count:
            sentiment = 'Позитивный'
        elif rating <= 2 or negative_count > positive_count:
            sentiment = 'Негативный'
        else:
            sentiment = 'Нейтральный'

        # Поиск проблем
        problems = [word for word in self.problem_keywords if word in text_lower]

        return {
            'sentiment': sentiment,
            'positive_words_count': positive_count,
            'negative_words_count': negative_count,
            'problems': problems,
            'rating': rating
        }

    def analyze_reviews_batch(self, reviews: List[Dict]) -> Dict:
        """
        Анализирует массив отзывов

        Args:
            reviews: список отзывов с ключами 'Текст отзыва' и 'Рейтинг'

        Returns:
            Dict с общей статистикой
        """
        if not reviews:
            return {
                'total_reviews': 0,
                'positive_reviews': 0,
                'negative_reviews': 0,
                'neutral_reviews': 0,
                'positive_percentage': 0,
                'negative_percentage': 0,
                'neutral_percentage': 0,
                'average_rating': 0,
                'rating_distribution': {},
                'reviews_with_problems': 0,
                'top_keywords': [],
                'top_problems': []
            }

        sentiments = {'Позитивный': 0, 'Негативный': 0, 'Нейтральный': 0}
        ratings = []
        all_problems = []
        reviews_with_problems = 0

        for review in reviews:
            text = str(review.get('Текст отзыва', ''))
            rating = int(review.get('Рейтинг', 3))
            ratings.append(rating)

            analysis = self.analyze_review(text, rating)
            sentiments[analysis['sentiment']] += 1

            if analysis['problems']:
                reviews_with_problems += 1
                all_problems.extend(analysis['problems'])

        # Распределение рейтингов
        rating_distribution = dict(Counter(ratings))

        # Топ проблем
        problem_counter = Counter(all_problems)
        top_problems = problem_counter.most_common(5)

        # Ключевые слова
        top_keywords = self.extract_key_phrases(reviews)

        # Средний рейтинг
        avg_rating = sum(ratings) / len(ratings) if ratings else 0
        total = len(reviews)

        return {
            'total_reviews': total,
            'positive_reviews': sentiments['Позитивный'],
            'negative_reviews': sentiments['Негативный'],
            'neutral_reviews': sentiments['Нейтральный'],
            'positive_percentage': round(sentiments['Позитивный'] / total * 100, 1) if total > 0 else 0,
            'negative_percentage': round(sentiments['Негативный'] / total * 100, 1) if total > 0 else 0,
            'neutral_percentage': round(sentiments['Нейтральный'] / total * 100, 1) if total > 0 else 0,
            'average_rating': round(avg_rating, 2),
            'rating_distribution': rating_distribution,
            'reviews_with_problems': reviews_with_problems,
            'top_keywords': top_keywords,
            'top_problems': top_problems
        }

    def extract_key_phrases(self, reviews: List[Dict], top_n: int = 10) -> List[tuple]:
        """
        Извлекает ключевые фразы из отзывов

        Args:
            reviews: список отзывов
            top_n: сколько фраз вернуть

        Returns:
            Список (фраза, количество)
        """
        # Простое извлечение слов (можно улучшить)
        all_words = []

        stop_words = {
            'и', 'в', 'на', 'с', 'по', 'для', 'не', 'что', 'это', 'как',
            'но', 'а', 'у', 'из', 'за', 'от', 'к', 'до', 'так', 'или',
            'же', 'о', 'бы', 'то', 'их', 'еще', 'уже', 'при', 'них'
        }

        for review in reviews:
            text = str(review.get('Текст отзыва', '')).lower()
            words = re.findall(r'\b[а-яё]{4,}\b', text)  # Слова от 4 букв
            all_words.extend([w for w in words if w not in stop_words])

        return Counter(all_words).most_common(top_n)

    def generate_summary(self, analysis: Dict) -> str:
        """
        Генерирует текстовое резюме анализа

        Args:
            analysis: результат analyze_reviews_batch

        Returns:
            Текстовое резюме
        """
        summary = []

        summary.append(f"📊 АНАЛИЗ ОТЗЫВОВ")
        summary.append(f"━━━━━━━━━━━━━━━━━━")
        summary.append(f"")
        summary.append(f"Всего отзывов: {analysis['total_reviews']}")
        summary.append(f"Средний рейтинг: {analysis['average_rating']} ⭐")
        summary.append(f"")
        summary.append(f"📈 Тональность:")
        summary.append(f"  😊 Позитивные: {analysis['positive_reviews']} ({analysis['positive_percentage']}%)")
        summary.append(f"  😐 Нейтральные: {analysis['neutral_reviews']} ({analysis['neutral_percentage']}%)")
        summary.append(f"  😞 Негативные: {analysis['negative_reviews']} ({analysis['negative_percentage']}%)")
        summary.append(f"")

        # Распределение рейтингов
        summary.append(f"⭐ Распределение рейтингов:")
        for rating in sorted(analysis['rating_distribution'].keys(), reverse=True):
            count = analysis['rating_distribution'][rating]
            stars = '⭐' * rating
            bar = '█' * (count // 5) if count > 0 else ''
            summary.append(f"  {stars} ({rating}): {count} {bar}")

        summary.append(f"")

        # Топ проблем
        if analysis['top_problems']:
            summary.append(f"⚠️ Частые проблемы:")
            for problem, count in analysis['top_problems']:
                summary.append(f"  • {problem}: {count}")

        return "\n".join(summary)
