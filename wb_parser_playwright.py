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

    def __init__(self, max_reviews: int = None):
        self.max_reviews = max_reviews or Config.MAX_REVIEWS
        logger.info(f"Инициализирован WB парсер с max_reviews={self.max_reviews}")

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
                print(f"🔍 Запрос: {url[:100]}", flush=True)

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

                    print(f"💬 Найден API вопросов: {url[:150]}", flush=True)
                    try:
                        data = await response.json()
                        keys = list(data.keys()) if isinstance(data, dict) else 'not dict'
                        print(f"📦 Структура ответа вопросов: {keys}", flush=True)

                        questions = None
                        if isinstance(data, dict):
                            # Проверяем различные варианты структуры WB API
                            questions = (
                                data.get('questions') or
                                data.get('data', {}).get('questions') if isinstance(data.get('data'), dict) else None or
                                data.get('feedbacks') or  # иногда WB использует feedbacks для вопросов тоже
                                data.get('qa') or
                                data.get('qna') or
                                data.get('questionList') or
                                data.get('items') or
                                data.get('result') or
                                []
                            )

                        if questions and isinstance(questions, list) and len(questions) > 0:
                            print(f"✅ Найдено {len(questions)} вопросов в API")

                            for q_data in questions:
                                if len(collected_questions) >= self.max_reviews:
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
                                    print(f"➕ Добавлен вопрос от {author}: {question_text[:30]}...")

                    except Exception as e:
                        print(f"⚠️ Ошибка парсинга API вопросов: {e}")

                # Ищем запросы к API отзывов (любые варианты)
                if ('/feedbacks' in url or '/feedback' in url or '/reviews' in url) and response.status == 200:
                    # Пропускаем статические файлы
                    content_type = response.headers.get('content-type', '')
                    if not content_type.startswith('application/json'):
                        return

                    print(f"✨ Найден API отзывов: {url[:100]}")
                    try:
                        data = await response.json()

                        # Проверяем разные варианты структуры ответа
                        feedbacks = None

                        if isinstance(data, dict):
                            # Вариант 1: {feedbacks: [...]}
                            feedbacks = data.get('feedbacks')

                            # Вариант 2: {data: {feedbacks: [...]}}
                            if not feedbacks and 'data' in data:
                                feedbacks = data['data'].get('feedbacks')

                            # Вариант 3: {reviews: [...]}
                            if not feedbacks:
                                feedbacks = data.get('reviews') or data.get('comments')

                            # Получаем общее количество
                            if not total_count:
                                total_count = (data.get('feedbackCount') or
                                             data.get('totalCount') or
                                             data.get('total') or 0)

                        if feedbacks and isinstance(feedbacks, list) and len(feedbacks) > 0:
                            print(f"✅ Найдено {len(feedbacks)} отзывов в API: {url[:80]}...")

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
                        print(f"⚠️ Ошибка парсинга API отзывов: {e}")

            # Подключаем перехватчик
            page.on('response', handle_response)

            try:
                print(f"🌐 Открываем страницу WB: {product_url}")

                # Открываем страницу и ждем загрузки сети
                await page.goto(product_url, wait_until='networkidle', timeout=30000)

                # Ждем еще немного для подгрузки отзывов
                await asyncio.sleep(2)

                # Пробуем прокрутить для загрузки большего количества отзывов
                # (если используется lazy loading)
                for i in range(5):
                    await page.evaluate('window.scrollBy(0, 1000)')
                    await asyncio.sleep(0.5)

                # Ищем и кликаем на вкладку "Вопросы"
                try:
                    print("💬 Пытаемся открыть вкладку с вопросами...", flush=True)

                    # Актуальные селекторы для WB (2026)
                    question_selectors = [
                        # По тексту
                        'text="Вопросы"',
                        'text="Вопросы о товаре"',
                        ':text("Вопрос")',
                        # По атрибутам data-*
                        '[data-link="questions"]',
                        '[data-tab="questions"]',
                        '[data-widget="Questions"]',
                        '[data-testid="questions-tab"]',
                        # По классам (общие паттерны WB)
                        '.product-page__tab:has-text("Вопрос")',
                        '.tabs__item:has-text("Вопрос")',
                        '.tab:has-text("Вопрос")',
                        # Ссылки и кнопки
                        'a:has-text("Вопросы")',
                        'button:has-text("Вопросы")',
                        'span:has-text("Вопросы")',
                        # Fallback - любой кликабельный элемент с текстом
                        '[role="tab"]:has-text("Вопрос")'
                    ]

                    clicked = False
                    for selector in question_selectors:
                        try:
                            element = await page.wait_for_selector(selector, timeout=1500, state='visible')
                            if element:
                                await element.click()
                                print(f"✅ Открыта вкладка вопросов через селектор: {selector}", flush=True)
                                clicked = True
                                break
                        except:
                            continue

                    if clicked:
                        # Ждём загрузки вопросов
                        await asyncio.sleep(3)
                        # Прокручиваем для загрузки всех вопросов
                        for i in range(5):
                            await page.evaluate('window.scrollBy(0, 800)')
                            await asyncio.sleep(0.7)
                        print(f"📜 Прокрутка вопросов завершена", flush=True)

                        # Если API не перехватил вопросы, парсим из DOM
                        if len(collected_questions) == 0:
                            print("🔍 API вопросов не найден, парсим из DOM...", flush=True)
                            dom_questions = await self._parse_questions_from_dom(page)
                            collected_questions.extend(dom_questions)
                            print(f"📝 Из DOM получено вопросов: {len(dom_questions)}", flush=True)
                    else:
                        print("ℹ️ Вкладка вопросов не найдена (возможно, у товара нет вопросов)", flush=True)
                except Exception as e:
                    print(f"⚠️ Ошибка при работе с вкладкой вопросов: {e}", flush=True)

                # Финальная пауза
                await asyncio.sleep(1)

                print(f"📊 Собрано отзывов: {len(collected_reviews)}")
                print(f"💬 Собрано вопросов: {len(collected_questions)}")

            except Exception as e:
                print(f"❌ Ошибка загрузки страницы: {e}")

            finally:
                await browser.close()

        return {
            'reviews': collected_reviews[:self.max_reviews],
            'questions': collected_questions[:self.max_reviews]
        }

    async def _parse_questions_from_dom(self, page) -> List[Dict]:
        """Парсит вопросы напрямую из DOM страницы (fallback если API не сработал)"""
        questions = []
        try:
            # Селекторы для блоков вопросов на WB (пробуем разные варианты)
            question_block_selectors = [
                '.questions__item',
                '.question-item',
                '.product-questions__item',
                '[data-widget="QuestionItem"]',
                '.qa-item',
                '.qna__item'
            ]

            for selector in question_block_selectors:
                elements = await page.query_selector_all(selector)
                if elements and len(elements) > 0:
                    print(f"✅ Найдены блоки вопросов по селектору: {selector} ({len(elements)} шт)", flush=True)

                    for elem in elements[:self.max_reviews]:
                        try:
                            # Пытаемся извлечь текст вопроса
                            q_text_el = await elem.query_selector('.question__text, .question-text, [class*="question"]')
                            q_text = await q_text_el.inner_text() if q_text_el else ''

                            # Пытаемся извлечь ответ
                            a_text_el = await elem.query_selector('.answer__text, .answer-text, [class*="answer"]')
                            a_text = await a_text_el.inner_text() if a_text_el else 'Нет ответа'

                            # Пытаемся извлечь автора
                            author_el = await elem.query_selector('.question__author, .author, [class*="user"]')
                            author = await author_el.inner_text() if author_el else 'Аноним'

                            # Пытаемся извлечь дату
                            date_el = await elem.query_selector('.question__date, .date, [class*="date"]')
                            date = await date_el.inner_text() if date_el else ''

                            if q_text:
                                questions.append({
                                    'question': q_text.strip(),
                                    'answer': a_text.strip() if a_text else 'Нет ответа',
                                    'author': author.strip() if author else 'Аноним',
                                    'date': date.strip() if date else ''
                                })
                        except Exception as e:
                            print(f"⚠️ Ошибка парсинга элемента вопроса: {e}", flush=True)
                            continue

                    if questions:
                        break  # Нашли вопросы, выходим

            # Если стандартные селекторы не сработали, пробуем универсальный подход
            if not questions:
                print("🔄 Пробуем универсальный парсинг вопросов...", flush=True)
                # Ищем любые элементы с текстом "вопрос" в классе
                all_questions = await page.evaluate('''() => {
                    const results = [];
                    // Ищем все элементы, которые могут быть вопросами
                    const elements = document.querySelectorAll('[class*="question"], [class*="Question"]');
                    elements.forEach(el => {
                        const text = el.innerText;
                        if (text && text.length > 10 && text.length < 2000) {
                            results.push(text);
                        }
                    });
                    return results.slice(0, 100);  // Максимум 100
                }''')

                if all_questions:
                    print(f"📝 Найдено {len(all_questions)} текстовых блоков с вопросами", flush=True)
                    for q_text in all_questions:
                        # Пробуем разделить на вопрос и ответ
                        parts = q_text.split('\n')
                        question = parts[0] if parts else q_text
                        answer = '\n'.join(parts[1:]) if len(parts) > 1 else 'Нет ответа'

                        questions.append({
                            'question': question.strip()[:500],
                            'answer': answer.strip()[:1000] if answer else 'Нет ответа',
                            'author': 'Аноним',
                            'date': ''
                        })

        except Exception as e:
            print(f"❌ Ошибка DOM-парсинга вопросов: {e}", flush=True)

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
