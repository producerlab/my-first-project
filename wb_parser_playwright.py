import asyncio
import logging
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from typing import List, Dict, Optional
import re
from datetime import datetime
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config import Config
from exceptions import (
    ParserError, NetworkError, PageLoadError,
    TimeoutError, RateLimitError, BrowserError,
    NoDataFoundError, APIResponseError
)

# Настройка логирования
logger = logging.getLogger(__name__)


class WildberriesParserPlaywright:
    """
    Парсер отзывов Wildberries через Playwright с перехватом API

    Этот парсер решает проблему закрытого API:
    1. Открывает реальную страницу товара в браузере
    2. Перехватывает API запросы к feedbacks, которые делает сам сайт WB
    3. Извлекает отзывы из ответов API

    Преимущества:
    - Работает с актуальным API WB (какой бы он ни был)
    - Не требует знания внутренних ID (imtId)
    - Обходит защиту от ботов
    """

    def __init__(self, max_reviews: int = None, max_questions: int = None):
        self.max_reviews = max_reviews or Config.MAX_REVIEWS
        self.max_questions = max_questions or Config.MAX_QUESTIONS
        logger.info(f"Инициализирован WB парсер с max_reviews={self.max_reviews}, max_questions={self.max_questions}")

    def extract_product_id(self, url: str) -> Optional[str]:
        """Извлекает ID товара из URL"""
        match = re.search(r'/catalog/(\d+)/', url)
        if match:
            return match.group(1)
        return None

    @retry(
        stop=stop_after_attempt(Config.RETRY_MAX_ATTEMPTS),
        wait=wait_exponential(
            multiplier=1,
            min=Config.RETRY_MIN_WAIT,
            max=Config.RETRY_MAX_WAIT
        ),
        retry=retry_if_exception_type((NetworkError, TimeoutError, BrowserError)),
        reraise=True
    )
    async def get_reviews(self, product_url: str, progress_callback=None) -> Dict[str, List[Dict]]:
        """
        Получает отзывы и вопросы перехватом API запросов с retry логикой

        Args:
            product_url: ссылка на товар
            progress_callback: функция для обновления прогресса (current, total)

        Returns:
            Dict с ключами 'reviews' и 'questions'

        Raises:
            InvalidURLError: Если URL невалидный
            PageLoadError: Если не удалось загрузить страницу
            NoDataFoundError: Если не найдено отзывов
            TimeoutError: Если превышен timeout
            NetworkError: Если проблемы с сетью
        """
        logger.info(f"Начало парсинга WB: {product_url}")
        collected_reviews = []
        collected_questions = []
        total_count = 0

        async with async_playwright() as p:
            # Запускаем браузер (headless из конфига)
            try:
                browser = await p.chromium.launch(
                    headless=Config.PARSER_HEADLESS,
                    args=['--disable-blink-features=AutomationControlled'],
                    timeout=Config.PARSER_TIMEOUT
                )
                logger.debug(f"Браузер запущен (headless={Config.PARSER_HEADLESS})")
            except Exception as e:
                logger.error(f"Ошибка запуска браузера: {e}")
                raise BrowserError(f"Не удалось запустить браузер: {str(e)}", browser_type="chromium")

            # Создаем контекст с реалистичными настройками
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
                locale='ru-RU'
            )

            page = await context.new_page()

            # Перехватчик ответов API
            async def handle_response(response):
                nonlocal collected_reviews, collected_questions, total_count

                url = response.url

                # Логируем ВСЕ запросы для отладки
                logger.debug(f"Запрос: {url[:100]}")

                # Обрабатываем вопросы - расширенный поиск по актуальным WB endpoints
                question_keywords = [
                    '/questions',
                    '/question',
                    'questions-api',
                    'feedbacks-api.wildberries.ru/api/v1/question',
                    '/qna',
                    '/qa'
                ]
                is_question_api = any(keyword in url.lower() for keyword in question_keywords)

                if is_question_api and response.status == 200:
                    # Пропускаем статические файлы (изображения, CSS, JS)
                    content_type = response.headers.get('content-type', '')
                    if not content_type.startswith('application/json'):
                        return

                    logger.info(f"Найден API вопросов: {url[:150]}")
                    try:
                        data = await response.json()
                        keys = list(data.keys()) if isinstance(data, dict) else 'not dict'
                        logger.info(f"Структура ответа вопросов: {keys}")

                        # Логируем для диагностики
                        if isinstance(data, dict):
                            for key in ['questions', 'data', 'feedbacks', 'items', 'result']:
                                if key in data:
                                    val = data[key]
                                    if isinstance(val, list):
                                        logger.info(f"  Ключ '{key}': список из {len(val)} элементов")
                                    elif isinstance(val, dict):
                                        logger.info(f"  Ключ '{key}': словарь с ключами {list(val.keys())[:5]}")

                        questions = None
                        if isinstance(data, dict):
                            # Проверяем различные варианты структуры WB API
                            questions = data.get('questions')
                            # Новый формат WB: questions может быть dict с вложенным списком
                            if isinstance(questions, dict):
                                questions = (
                                    questions.get('items') or
                                    questions.get('list') or
                                    questions.get('data') or
                                    questions.get('questions') or
                                    []
                                )
                            if not questions and isinstance(data.get('data'), dict):
                                questions = data['data'].get('questions')
                                if isinstance(questions, dict):
                                    questions = questions.get('items') or questions.get('list') or []
                            if not questions:
                                questions = (
                                    data.get('feedbacks') or
                                    data.get('qa') or
                                    data.get('qna') or
                                    data.get('questionList') or
                                    data.get('items') or
                                    data.get('result') or
                                    []
                                )

                        # Диагностика: что в итоге получили
                        logger.info(f"Тип questions: {type(questions).__name__}, "
                                    f"длина: {len(questions) if hasattr(questions, '__len__') else 'N/A'}")

                        if questions and isinstance(questions, list) and len(questions) > 0:
                            logger.info(f"Найдено {len(questions)} вопросов в API")

                            for q_data in questions:
                                if len(collected_questions) >= self.max_questions:
                                    break

                                # Извлекаем текст вопроса
                                question_text = (q_data.get('text') or
                                               q_data.get('question') or
                                               q_data.get('questionText') or
                                               q_data.get('body') or '')

                                # Извлекаем ответ (может быть вложенным объектом)
                                answer_data = q_data.get('answer')
                                if isinstance(answer_data, dict):
                                    answer_text = answer_data.get('text') or answer_data.get('body') or 'Нет ответа'
                                elif isinstance(answer_data, str):
                                    answer_text = answer_data
                                elif isinstance(answer_data, list) and len(answer_data) > 0:
                                    # Иногда ответов может быть несколько
                                    first_answer = answer_data[0]
                                    answer_text = first_answer.get('text') if isinstance(first_answer, dict) else str(first_answer)
                                else:
                                    answer_text = 'Нет ответа'

                                # Извлекаем автора
                                user_data = q_data.get('user')
                                if isinstance(user_data, dict):
                                    author = user_data.get('name') or user_data.get('username') or 'Аноним'
                                else:
                                    author = q_data.get('userName') or q_data.get('author') or 'Аноним'

                                question = {
                                    'question': question_text,
                                    'answer': answer_text,
                                    'date': (q_data.get('createdDate') or
                                           q_data.get('date') or
                                           q_data.get('created') or ''),
                                    'author': author
                                }

                                if question['question']:
                                    collected_questions.append(question)
                                    logger.debug(f"Добавлен вопрос от {author}: {question_text[:30]}...")

                    except Exception as e:
                        logger.warning(f"Ошибка парсинга API вопросов: {e}")

                # Ищем запросы к API отзывов (любые варианты)
                feedback_keywords = ['/feedbacks', '/feedback', '/reviews', '/comments', 'feedbacks-api']
                is_feedback_api = any(keyword in url.lower() for keyword in feedback_keywords)

                if is_feedback_api and response.status == 200:
                    # Пропускаем статические файлы
                    content_type = response.headers.get('content-type', '')
                    if not content_type.startswith('application/json'):
                        return

                    logger.info(f"Найден API отзывов: {url[:150]}")
                    try:
                        data = await response.json()
                        keys = list(data.keys()) if isinstance(data, dict) else 'not dict'
                        logger.info(f"Структура ответа отзывов: {keys}")

                        # Логируем для диагностики
                        if isinstance(data, dict):
                            for key in ['feedbacks', 'data', 'reviews', 'comments', 'items', 'result']:
                                if key in data:
                                    val = data[key]
                                    if isinstance(val, list):
                                        logger.info(f"  Ключ '{key}': список из {len(val)} элементов")
                                    elif isinstance(val, dict):
                                        logger.info(f"  Ключ '{key}': словарь с ключами {list(val.keys())[:5]}")

                        # Проверяем разные варианты структуры ответа
                        feedbacks = None

                        if isinstance(data, dict):
                            # Вариант 1: {feedbacks: [...]}
                            feedbacks = data.get('feedbacks')

                            # Вариант 2: {data: {feedbacks: [...]}}
                            if not feedbacks and 'data' in data and isinstance(data['data'], dict):
                                feedbacks = data['data'].get('feedbacks')

                            # Вариант 3: {reviews: [...]} или другие варианты
                            if not feedbacks:
                                feedbacks = (
                                    data.get('reviews') or
                                    data.get('comments') or
                                    data.get('items') or
                                    data.get('result')
                                )

                            # Получаем общее количество
                            if not total_count:
                                total_count = (data.get('feedbackCount') or
                                             data.get('feedbackCountWithText') or
                                             data.get('totalCount') or
                                             data.get('total') or
                                             data.get('count') or 0)

                        if feedbacks and isinstance(feedbacks, list) and len(feedbacks) > 0:
                            logger.info(f"Найдено {len(feedbacks)} отзывов в API")

                            for feedback in feedbacks:
                                if len(collected_reviews) >= self.max_reviews:
                                    break

                                # Адаптивное извлечение данных
                                review = {
                                    'text': (feedback.get('text') or
                                           feedback.get('comment') or
                                           feedback.get('message') or ''),
                                    'rating': (feedback.get('productValuation') or
                                             feedback.get('rating') or
                                             feedback.get('rate') or 0),
                                    'date': (feedback.get('createdDate') or
                                           feedback.get('date') or
                                           feedback.get('created_at') or ''),
                                    'author': (feedback.get('wbUserDetails', {}).get('name') or
                                             feedback.get('author') or
                                             feedback.get('userName') or
                                             feedback.get('user') or 'Аноним'),
                                    'pros': feedback.get('pros') or feedback.get('advantages') or '',
                                    'cons': feedback.get('cons') or feedback.get('disadvantages') or ''
                                }

                                # Добавляем только если есть хоть какой-то текст
                                if review['text'] or review['pros'] or review['cons']:
                                    collected_reviews.append(review)

                            # Обновляем прогресс
                            if progress_callback:
                                await progress_callback(len(collected_reviews),
                                                       min(total_count or self.max_reviews, self.max_reviews))

                    except Exception as e:
                        # Не JSON или ошибка парсинга
                        logger.warning(f"Ошибка парсинга API отзывов: {e}")

            # Подключаем перехватчик
            page.on('response', handle_response)

            try:
                logger.info(f"Открываем страницу WB: {product_url}")

                # Открываем страницу (networkidle на WB не достигается — используем domcontentloaded)
                await page.goto(product_url, wait_until='domcontentloaded', timeout=30000)

                # Ждем подгрузки данных
                await asyncio.sleep(3)

                # Извлекаем артикул из URL
                product_id = self.extract_product_id(product_url)

                # Переходим на страницу отзывов напрямую по URL
                if product_id:
                    try:
                        logger.info("Переходим на страницу отзывов...")
                        feedbacks_url = f"https://www.wildberries.ru/catalog/{product_id}/feedbacks"
                        logger.debug(f"URL отзывов: {feedbacks_url}")

                        await page.goto(feedbacks_url, wait_until='domcontentloaded', timeout=30000)
                        await asyncio.sleep(2)

                        # Прокручиваем для загрузки всех отзывов
                        for i in range(8):
                            await page.evaluate('window.scrollBy(0, 1500)')
                            await asyncio.sleep(1.0)
                        # Финальная пауза — дать поздним API-ответам прийти
                        await asyncio.sleep(3)
                        logger.debug("Прокрутка страницы отзывов завершена")
                    except Exception as e:
                        logger.warning(f"Ошибка при загрузке страницы отзывов: {e}")

                # Переходим на страницу вопросов напрямую по URL
                if product_id:
                    try:
                        logger.info("Переходим на страницу вопросов...")
                        questions_url = f"https://www.wildberries.ru/catalog/{product_id}/questions"
                        logger.debug(f"URL вопросов: {questions_url}")

                        # Открываем страницу вопросов
                        await page.goto(questions_url, wait_until='domcontentloaded', timeout=30000)
                        await asyncio.sleep(3)

                        # Прокручиваем для загрузки всех вопросов
                        for i in range(8):
                            await page.evaluate('window.scrollBy(0, 1500)')
                            await asyncio.sleep(1.0)
                        # Финальная пауза — дать поздним API-ответам с вопросами прийти
                        await asyncio.sleep(3)
                        logger.debug("Прокрутка страницы вопросов завершена")

                        # Если API не перехватил вопросы, парсим из DOM
                        if len(collected_questions) == 0:
                            logger.info("API вопросов не найден, парсим из DOM...")
                            dom_questions = await self._parse_questions_from_dom(page)
                            collected_questions.extend(dom_questions)
                            logger.info(f"Из DOM получено вопросов: {len(dom_questions)}")
                    except Exception as e:
                        logger.warning(f"Ошибка при загрузке страницы вопросов: {e}")
                else:
                    logger.warning("Не удалось извлечь артикул товара из URL")

                # Финальная пауза
                await asyncio.sleep(1)

                logger.info(f"Собрано отзывов: {len(collected_reviews)}")
                logger.info(f"Собрано вопросов: {len(collected_questions)}")

            except Exception as e:
                logger.error(f"Ошибка загрузки страницы: {e}")

            finally:
                await browser.close()

        return {
            'reviews': collected_reviews[:self.max_reviews],
            'questions': collected_questions[:self.max_questions]
        }

    async def _parse_questions_from_dom(self, page) -> List[Dict]:
        """Парсит вопросы напрямую из DOM страницы"""
        questions = []
        try:
            logger.debug("Парсим содержимое страницы вопросов...")

            # Собираем ВСЕ текстовые блоки на странице, которые могут быть вопросами
            # Ищем повторяющиеся структуры (карточки вопросов)
            page_content = await page.evaluate('''() => {
                const results = [];
                const seen = new Set();

                // Функция для проверки, является ли текст "мусором"
                const isJunk = (text) => {
                    if (!text || text.length < 10 || text.length > 3000) return true;
                    // Исключаем навигацию, кнопки, счётчики
                    const junkPatterns = [
                        /^\\d+\\s*(вопрос|отзыв|товар)/i,
                        /^(вопрос|отзыв|показать|загрузить|ещё|далее|назад)/i,
                        /^(главная|каталог|корзина|избранное|профиль)/i,
                        /^\\d+$/,
                        /^(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)$/i
                    ];
                    return junkPatterns.some(p => p.test(text.trim()));
                };

                // Способ 1: Ищем все li элементы (списки вопросов)
                document.querySelectorAll('ul > li, ol > li').forEach(li => {
                    const text = li.innerText?.trim();
                    if (text && !isJunk(text) && text.length > 20) {
                        const key = text.substring(0, 100);
                        if (!seen.has(key)) {
                            seen.add(key);
                            results.push({ text, tag: 'li' });
                        }
                    }
                });

                // Способ 2: Ищем article элементы
                document.querySelectorAll('article').forEach(article => {
                    const text = article.innerText?.trim();
                    if (text && !isJunk(text) && text.length > 20) {
                        const key = text.substring(0, 100);
                        if (!seen.has(key)) {
                            seen.add(key);
                            results.push({ text, tag: 'article' });
                        }
                    }
                });

                // Способ 3: Ищем div с классами содержащими item, card, block
                document.querySelectorAll('[class*="item"], [class*="card"], [class*="block"]').forEach(el => {
                    // Пропускаем если это контейнер с множеством дочерних элементов того же типа
                    if (el.querySelectorAll('[class*="item"], [class*="card"]').length > 2) return;

                    const text = el.innerText?.trim();
                    if (text && !isJunk(text) && text.length > 30 && text.length < 1500) {
                        const key = text.substring(0, 100);
                        if (!seen.has(key)) {
                            seen.add(key);
                            results.push({ text, tag: el.className.split(' ')[0] || 'div' });
                        }
                    }
                });

                return results.slice(0, 200);
            }''')

            logger.debug(f"Найдено {len(page_content)} текстовых блоков на странице")

            if page_content:
                # Логируем первые 3 для диагностики
                for i, item in enumerate(page_content[:3]):
                    text_preview = item.get('text', '')[:80].replace('\n', ' ')
                    logger.debug(f"  [{i+1}] ({item.get('tag')}): {text_preview}...")

                # Обрабатываем найденные блоки
                for item in page_content:
                    text = item.get('text', '')
                    lines = [l.strip() for l in text.split('\n') if l.strip() and len(l.strip()) > 3]

                    if len(lines) >= 1:
                        # Первая строка - вопрос, остальное - ответ
                        question_text = lines[0]

                        # Пропускаем если это явно не вопрос
                        skip_words = ['вопросов', 'вопроса', 'отзывов', 'отзыва', 'товаров', 'рубл', '₽', 'корзин']
                        if any(w in question_text.lower() for w in skip_words) and len(question_text) < 50:
                            continue

                        answer_text = '\n'.join(lines[1:]) if len(lines) > 1 else 'Нет ответа'

                        questions.append({
                            'question': question_text[:500],
                            'answer': answer_text[:1000] if answer_text else 'Нет ответа',
                            'author': 'Аноним',
                            'date': ''
                        })

            logger.debug(f"Отфильтровано вопросов: {len(questions)}")

        except Exception as e:
            logger.error(f"Ошибка DOM-парсинга вопросов: {e}")

        return questions

    def format_reviews_for_excel(self, reviews: List[Dict]) -> List[Dict]:
        """Форматирует отзывы для записи в Excel"""
        formatted = []
        for review in reviews:
            formatted.append({
                'Автор': review['author'],
                'Рейтинг': review['rating'],
                'Дата': review['date'][:10] if review['date'] else '',
                'Текст отзыва': review['text'],
                'Плюсы': review['pros'],
                'Минусы': review['cons']
            })
        return formatted

    def format_questions_for_excel(self, questions: List[Dict]) -> List[Dict]:
        """Форматирует вопросы для записи в Excel в формате отзывов"""
        formatted = []
        for q in questions:
            # Приводим к формату отзывов для совместимости с export_reviews
            formatted.append({
                'Автор': q.get('author', 'Аноним'),
                'Рейтинг': 0,  # У вопросов нет рейтинга
                'Дата': q.get('date', '')[:10] if q.get('date') else '',
                'Текст отзыва': f"❓ {q.get('question', '')}\n\n💬 {q.get('answer', 'Нет ответа')}",
                'Плюсы': '',
                'Минусы': ''
            })
        return formatted


def filter_reviews_by_rating(reviews: List[Dict], filter_type: str) -> List[Dict]:
    """Фильтрует отзывы по рейтингу (поле 'rating', int 1-5).

    filter_type:
      'all'                 — без фильтрации
      '1'..'5'              — одна оценка
      '1-2' / '1-3' / '4-5' — диапазон
      '2,5'                 — произвольный набор (ручной выбор)
    Неизвестный filter_type возвращает список без изменений.
    """
    if not filter_type or filter_type == 'all':
        return reviews

    if ',' in filter_type:
        try:
            allowed = {int(x) for x in filter_type.split(',')}
        except ValueError:
            return reviews
        return [r for r in reviews if r.get('rating') in allowed]

    ranges = {'1-2': {1, 2}, '1-3': {1, 2, 3}, '4-5': {4, 5}}
    if filter_type in ranges:
        allowed = ranges[filter_type]
        return [r for r in reviews if r.get('rating') in allowed]

    try:
        star = int(filter_type)
    except ValueError:
        return reviews
    if not 1 <= star <= 5:
        return reviews
    return [r for r in reviews if r.get('rating') == star]

