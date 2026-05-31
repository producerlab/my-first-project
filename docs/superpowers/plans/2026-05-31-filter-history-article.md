# Фильтр по звёздам, /history, приём артикула, сводка — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить в бота фильтр отзывов по звёздам (кнопки до сбора), `/history` с повторной отправкой через Telegram `file_id`, приём чистого артикула и сводку после сбора.

**Architecture:** Поток обработки товара получает промежуточный FSM-шаг (`MemoryStorage` уже подключён): `handle_url` валидирует и показывает кнопки фильтра, callback запускает сбор. Фильтрация — чистая функция в парсере на его же выходных данных (`rating` — int). История — последние 5 успешных запусков, файлы повторно отправляются по сохранённому `file_id` без диска и пересбора.

**Tech Stack:** Python 3.11, aiogram 3 (FSM: `StatesGroup`/`FSMContext`), SQLite, pytest.

> **ВАЖНО — расхождение спека с реальностью кодовой базы:** CLAUDE.md описывает `supabase_database.py` и двойную БД, но этого файла в репозитории НЕТ — есть только `database.py` (SQLite). Поэтому изменения схемы вносятся только в `database.py`. FSM подключён частично: `MemoryStorage` и `Dispatcher(storage=storage)` уже есть в `bot.py`, но `StatesGroup`/`FSMContext` ещё не используются — этот план их добавляет.

---

## File Structure

| Файл | Ответственность | Изменение |
|------|-----------------|-----------|
| `wb_parser_playwright.py` | `filter_reviews_by_rating()` — чистая фильтрация по рейтингу | Modify (добавить функцию модуля) |
| `url_validator.py` | Приём чистого артикула → канонический URL | Modify |
| `database.py` | Миграция схемы `requests`, новые поля в `add_request`/`get_recent_requests` | Modify |
| `bot.py` | FSM-состояние, клавиатуры фильтра, callback'и, `/history`, `run_collection`, `/help`, `/cancel` | Modify |
| `tests/test_filter.py` | Тесты `filter_reviews_by_rating` | Create |
| `tests/test_url_validator.py` | Тесты приёма артикула | Modify |
| `tests/test_database.py` | Тесты миграции и новых полей | Modify |

Порядок задач: сначала чистые модули с лёгкими тестами (фильтр, артикул, БД), затем интеграция в `bot.py`.

---

## Task 1: Чистая функция фильтрации по рейтингу

**Files:**
- Modify: `wb_parser_playwright.py` (добавить функцию уровня модуля в конец файла)
- Test: `tests/test_filter.py`

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_filter.py`:

```python
from wb_parser_playwright import filter_reviews_by_rating


def _reviews():
    return [
        {'rating': 1, 'text': 'a'},
        {'rating': 2, 'text': 'b'},
        {'rating': 3, 'text': 'c'},
        {'rating': 4, 'text': 'd'},
        {'rating': 5, 'text': 'e'},
        {'rating': 0, 'text': 'no rating'},
    ]


def test_all_returns_everything():
    assert filter_reviews_by_rating(_reviews(), 'all') == _reviews()


def test_single_star():
    result = filter_reviews_by_rating(_reviews(), '3')
    assert [r['rating'] for r in result] == [3]


def test_range_1_2():
    result = filter_reviews_by_rating(_reviews(), '1-2')
    assert [r['rating'] for r in result] == [1, 2]


def test_range_1_3():
    result = filter_reviews_by_rating(_reviews(), '1-3')
    assert [r['rating'] for r in result] == [1, 2, 3]


def test_range_4_5():
    result = filter_reviews_by_rating(_reviews(), '4-5')
    assert [r['rating'] for r in result] == [4, 5]


def test_custom_set():
    result = filter_reviews_by_rating(_reviews(), '2,5')
    assert [r['rating'] for r in result] == [2, 5]


def test_empty_list():
    assert filter_reviews_by_rating([], '1-3') == []


def test_rating_zero_excluded_by_filters():
    # отзыв с rating=0 не попадает ни в один числовой фильтр
    result = filter_reviews_by_rating(_reviews(), '1-3')
    assert all(r['rating'] != 0 for r in result)


def test_unknown_filter_returns_all():
    # некорректный filter_type не должен ронять — возвращаем как есть
    assert filter_reviews_by_rating(_reviews(), 'garbage') == _reviews()
```

- [ ] **Step 2: Запустить тест — убедиться что падает**

Run: `pytest tests/test_filter.py -v`
Expected: FAIL — `ImportError: cannot import name 'filter_reviews_by_rating'`

- [ ] **Step 3: Реализовать функцию**

В конец `wb_parser_playwright.py` (функция уровня модуля, вне класса):

```python
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
    return [r for r in reviews if r.get('rating') == star]
```

- [ ] **Step 4: Запустить тест — убедиться что проходит**

Run: `pytest tests/test_filter.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Коммит**

```bash
git add wb_parser_playwright.py tests/test_filter.py
git commit -m "feat: фильтрация отзывов по рейтингу (чистая функция)"
```

---

## Task 2: Приём чистого артикула в URLValidator

**Files:**
- Modify: `url_validator.py` (метод `sanitize_url`, строки 131-156)
- Test: `tests/test_url_validator.py`

- [ ] **Step 1: Написать падающий тест**

Добавить в `tests/test_url_validator.py`:

```python
def test_bare_article_expands_to_canonical_url():
    result = URLValidator.sanitize_url('12345678')
    assert result == 'https://www.wildberries.ru/catalog/12345678/detail.aspx'


def test_bare_article_validates_as_wildberries():
    url = URLValidator.sanitize_url('12345678')
    marketplace, product_id = URLValidator.validate_url(url)
    assert marketplace == 'wildberries'
    assert product_id == '12345678'


def test_bare_article_with_whitespace():
    assert URLValidator.sanitize_url('  12345678  ') == \
        'https://www.wildberries.ru/catalog/12345678/detail.aspx'


def test_too_short_digits_not_treated_as_article():
    # 5 цифр — не артикул, остаётся как есть (и потом упадёт валидация)
    assert URLValidator.sanitize_url('12345') == '12345'


def test_normal_url_unchanged():
    url = 'https://www.wildberries.ru/catalog/12345678/detail.aspx'
    assert URLValidator.sanitize_url(url) == url
```

(в начале файла должен быть `from url_validator import URLValidator` — проверить, что он уже есть)

- [ ] **Step 2: Запустить тест — убедиться что падает**

Run: `pytest tests/test_url_validator.py -k bare_article -v`
Expected: FAIL — `sanitize_url('12345678')` возвращает `'12345678'`, а не canonical URL

- [ ] **Step 3: Реализовать**

В `url_validator.py`, в методе `sanitize_url`, сразу после `url = url.strip()` (строка 143) добавить:

```python
        # Чистый артикул (6-12 цифр) → канонический URL товара WB
        if url.isdigit() and 6 <= len(url) <= 12:
            return f'https://www.wildberries.ru/catalog/{url}/detail.aspx'
```

- [ ] **Step 4: Запустить тесты — убедиться что проходят**

Run: `pytest tests/test_url_validator.py -v`
Expected: PASS (все прежние + 5 новых)

- [ ] **Step 5: Коммит**

```bash
git add url_validator.py tests/test_url_validator.py
git commit -m "feat: приём чистого артикула WB наравне со ссылкой"
```

---

## Task 3: Миграция БД и расширение методов

**Files:**
- Modify: `database.py` (`init_database` строки 13-57, `add_request` строки 83-108, `get_recent_requests` строки 170-195)
- Test: `tests/test_database.py`

- [ ] **Step 1: Написать падающий тест**

Добавить в `tests/test_database.py` (использует временную БД — посмотреть как существующие тесты создают `Database`, повторить тот же приём с `tmp_path`):

```python
def test_add_request_stores_new_fields(tmp_path):
    db = Database(db_path=str(tmp_path / "t.db"))
    db.add_or_update_user(1, "u", "f", "l")
    db.add_request(
        user_id=1, marketplace="Wildberries",
        product_url="https://www.wildberries.ru/catalog/12345678/detail.aspx",
        reviews_count=33, success=True,
        filter_type="1-3", questions_count=32, avg_rating=2.1,
        reviews_file_id="REV_FILE_ID", questions_file_id="Q_FILE_ID",
    )
    rows = db.get_recent_requests(1, limit=5)
    assert len(rows) == 1
    r = rows[0]
    assert r['filter_type'] == "1-3"
    assert r['questions_count'] == 32
    assert r['avg_rating'] == 2.1
    assert r['reviews_file_id'] == "REV_FILE_ID"
    assert r['questions_file_id'] == "Q_FILE_ID"
    assert 'id' in r


def test_add_request_backward_compatible(tmp_path):
    # старый вызов без новых полей по-прежнему работает
    db = Database(db_path=str(tmp_path / "t2.db"))
    db.add_or_update_user(2, "u", "f", "l")
    db.add_request(2, "Wildberries", "https://x", 0, success=False,
                   error_message="нет данных")
    rows = db.get_recent_requests(2, limit=5)
    assert rows[0]['success'] is False
```

- [ ] **Step 2: Запустить тест — убедиться что падает**

Run: `pytest tests/test_database.py -k "new_fields or backward" -v`
Expected: FAIL — `add_request() got an unexpected keyword argument 'filter_type'`

- [ ] **Step 3: Добавить миграцию в `init_database`**

В `database.py`, в `init_database`, перед `conn.commit()` (строка 56) добавить идемпотентную миграцию:

```python
        # Миграция: добавляем новые колонки, если их ещё нет (старая БД)
        cursor.execute("PRAGMA table_info(requests)")
        existing_cols = {row[1] for row in cursor.fetchall()}
        new_cols = {
            'filter_type': "TEXT",
            'questions_count': "INTEGER DEFAULT 0",
            'avg_rating': "REAL DEFAULT 0",
            'reviews_file_id': "TEXT",
            'questions_file_id': "TEXT",
        }
        for col, decl in new_cols.items():
            if col not in existing_cols:
                cursor.execute(f"ALTER TABLE requests ADD COLUMN {col} {decl}")
```

- [ ] **Step 4: Расширить `add_request`**

Заменить сигнатуру и тело `add_request` (строки 83-108) на:

```python
    def add_request(
        self,
        user_id: int,
        marketplace: str,
        product_url: str,
        reviews_count: int,
        success: bool = True,
        error_message: str = None,
        filter_type: str = None,
        questions_count: int = 0,
        avg_rating: float = 0,
        reviews_file_id: str = None,
        questions_file_id: str = None
    ):
        """Добавляет запрос в историю и обновляет счётчик пользователя"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO requests (
                user_id, marketplace, product_url, reviews_count, success, error_message,
                filter_type, questions_count, avg_rating, reviews_file_id, questions_file_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, marketplace, product_url, reviews_count, 1 if success else 0,
              error_message, filter_type, questions_count, avg_rating,
              reviews_file_id, questions_file_id))

        cursor.execute('''
            UPDATE users SET total_requests = total_requests + 1 WHERE user_id = ?
        ''', (user_id,))

        conn.commit()
        conn.close()
```

- [ ] **Step 5: Расширить `get_recent_requests`**

Заменить тело `get_recent_requests` (строки 170-195) на:

```python
    def get_recent_requests(self, user_id: int, limit: int = 5) -> List[Dict]:
        """Получает последние запросы пользователя"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT id, marketplace, product_url, reviews_count, created_at, success,
                   filter_type, questions_count, avg_rating,
                   reviews_file_id, questions_file_id
            FROM requests
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        ''', (user_id, limit))

        rows = cursor.fetchall()
        conn.close()

        return [
            {
                'id': row[0],
                'marketplace': row[1],
                'product_url': row[2],
                'reviews_count': row[3],
                'created_at': row[4],
                'success': bool(row[5]),
                'filter_type': row[6],
                'questions_count': row[7],
                'avg_rating': row[8],
                'reviews_file_id': row[9],
                'questions_file_id': row[10],
            }
            for row in rows
        ]
```

- [ ] **Step 6: Запустить тесты — убедиться что проходят**

Run: `pytest tests/test_database.py -v`
Expected: PASS (прежние 14 + 2 новых)

- [ ] **Step 7: Коммит**

```bash
git add database.py tests/test_database.py
git commit -m "feat: поля filter_type/questions_count/avg_rating/file_id в requests + миграция"
```

---

## Task 4: FSM-состояние и клавиатуры фильтра

**Files:**
- Modify: `bot.py` (добавить импорты FSM и определения после строки 76, до handlers)

- [ ] **Step 1: Добавить импорты FSM и InlineKeyboard**

В `bot.py` в блок импортов aiogram (после строки 8 `from aiogram.types import Message, FSInputFile`) добавить:

```python
from aiogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
```

- [ ] **Step 2: Определить состояние, пресеты и клавиатуры**

После блока настроек (после `active_tasks = {}`, строка ~76) добавить:

```python
# ─── Фильтр отзывов по звёздам ────────────────────────────────────────────────
class CollectStates(StatesGroup):
    waiting_filter = State()


FILTER_LABELS = {
    "all": "⭐ Все отзывы",
    "1": "1★",
    "1-2": "1–2★",
    "1-3": "1–3★",
    "4-5": "4–5★",
}


def build_filter_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⭐ Все отзывы", callback_data="flt:all")
    builder.button(text="1★", callback_data="flt:1")
    builder.button(text="1–2★", callback_data="flt:1-2")
    builder.button(text="1–3★", callback_data="flt:1-3")
    builder.button(text="4–5★", callback_data="flt:4-5")
    builder.button(text="🔢 Выбрать вручную", callback_data="flt:custom")
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()


def build_star_keyboard(selected: set) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for star in range(1, 6):
        mark = "✅ " if star in selected else ""
        builder.button(text=f"{mark}{star}★", callback_data=f"star:{star}")
    builder.button(text="✅ Готово", callback_data="flt:done")
    builder.button(text="🔙 Назад", callback_data="flt:back")
    builder.adjust(5, 2)
    return builder.as_markup()


def filter_label(filter_type: str) -> str:
    """Человекочитаемая метка фильтра (для сводки и /history)."""
    if filter_type in FILTER_LABELS:
        return FILTER_LABELS[filter_type]
    if filter_type and "," in filter_type:
        return "★ " + ", ".join(f"{s}★" for s in filter_type.split(","))
    return f"{filter_type}★" if filter_type else "⭐ Все отзывы"
```

- [ ] **Step 3: Проверить импортируемость**

Run: `python -c "import bot"`
Expected: без ошибок импорта (бот не запускается, только импорт модуля). Если падает на отсутствии BOT_TOKEN — установить фиктивный: `BOT_TOKEN=dummy python -c "import bot"`.

- [ ] **Step 4: Коммит**

```bash
git add bot.py
git commit -m "feat: FSM-состояние и клавиатуры фильтра по звёздам"
```

---

## Task 5: Переработать handle_url под выбор фильтра

**Files:**
- Modify: `bot.py` (`handle_url` строки 242-447 — разделить на валидацию+кнопки и `run_collection`)

Это самая крупная задача. `handle_url` сейчас делает всё подряд (строки 242-447). Разделяем: `handle_url` доводит до показа кнопок и сохранения данных в FSM; новая `run_collection` выполняет сбор. Тело сбора (парсинг → Excel → отправка) переносится в `run_collection` почти без изменений, добавляются: фильтрация, сводка, сохранение file_id.

- [ ] **Step 1: Заменить сигнатуру и тело handle_url (валидация → кнопки)**

Заменить весь блок `handle_url` (строки 242-447) на две функции. Сначала `handle_url`:

```python
@dp.message(F.text, F.chat.type == "private")
async def handle_url(message: Message, state: FSMContext):
    """Принимает ссылку или артикул, валидирует, проверяет подписку,
    показывает кнопки фильтра. Сбор запускается после выбора фильтра."""
    user_id = message.from_user.id
    username = message.from_user.username or "Unknown"
    raw = message.text.strip()

    db.add_or_update_user(
        user_id, message.from_user.username,
        message.from_user.first_name, message.from_user.last_name
    )
    logger.info(f"Пользователь {user_id} ({username}) отправил: {raw}")

    try:
        sanitized_url = URLValidator.sanitize_url(raw)
        marketplace_code, product_id = URLValidator.validate_url(sanitized_url)
        url = sanitized_url
    except InvalidURLError as e:
        logger.warning(f"Невалидный ввод от {user_id}: {e}")
        await message.answer(f"❌ {e.reason}\n\nИспользуйте /help для инструкций.")
        return

    if marketplace_code != 'wildberries':
        await message.answer("❌ Пока поддерживается только Wildberries.\n\nПоддержка Ozon скоро появится!")
        return

    is_subscribed = await check_subscription(user_id)
    if not is_subscribed:
        await message.answer(
            "❌ Для использования бота необходимо подписаться на наш канал!\n\n"
            f"📢 Канал: {REQUIRED_CHANNEL}\n"
            f"🔗 Ссылка: https://t.me/khosnullin_channel\n\n"
            "После подписки отправьте ссылку снова."
        )
        return

    # Сохраняем контекст и показываем кнопки фильтра.
    # Rate-limit спишем после выбора фильтра (в callback).
    await state.set_state(CollectStates.waiting_filter)
    await state.update_data(
        url=url, product_id=product_id, marketplace='Wildberries', custom_stars=[]
    )
    await message.answer(
        f"✅ <b>Товар найден!</b> Артикул: <code>{product_id}</code>\n\n"
        "Выберите фильтр для отзывов (вопросы собираются всегда полностью):",
        reply_markup=build_filter_keyboard(),
        parse_mode="HTML",
    )
```

- [ ] **Step 2: Добавить run_collection (тело сбора)**

Сразу после `handle_url` добавить `run_collection`. Это перенос прежнего тела сбора (строки 312-447) с тремя добавлениями: фильтрация отзывов, сводка, сохранение file_id. Импорт фильтра — вверху файла: добавить `filter_reviews_by_rating` к `from wb_parser_playwright import ...`.

```python
async def run_collection(message: Message, user_id: int, data: dict):
    """Выполняет сбор: парсинг → фильтрация → Excel → отправка → сводка → file_id."""
    url = data['url']
    product_id = data['product_id']
    marketplace = data['marketplace']
    filter_type = data['filter']
    parser = wb_parser

    active_tasks[user_id] = {'cancelled': False, 'marketplace': marketplace}

    can_request, remaining = db.check_rate_limit(user_id, RATE_LIMIT_REQUESTS, RATE_LIMIT_HOURS)
    if not can_request:
        await message.answer(
            f"⛔ Вы превысили лимит запросов!\n\n"
            f"Доступно: {RATE_LIMIT_REQUESTS} запросов в {RATE_LIMIT_HOURS} час."
        )
        active_tasks.pop(user_id, None)
        return
    db.add_rate_limit_record(user_id)

    status_msg = await message.answer(
        f"⏳ Начинаю сбор отзывов с {marketplace}...\n"
        f"Осталось запросов: {remaining - 1}/{RATE_LIMIT_REQUESTS}\n\n"
        f"Для отмены используйте /cancel"
    )

    async def update_progress(current: int, total: int):
        try:
            if total > 0:
                percentage = (current / total) * 100
                filled = int(20 * current / total)
                bar = '█' * filled + '░' * (20 - filled)
                await status_msg.edit_text(
                    f"⏳ Собираю отзывы с {marketplace}...\n\n"
                    f"📊 Прогресс: {current}/{total} ({percentage:.1f}%)\n{bar}"
                )
        except Exception as e:
            logger.error(f"Ошибка обновления прогресса: {e}")

    try:
        result = await parser.get_reviews(url, progress_callback=update_progress)

        if user_id in active_tasks and active_tasks[user_id]['cancelled']:
            await status_msg.edit_text("⛔ Парсинг отменён")
            active_tasks.pop(user_id, None)
            return

        reviews_all = result.get('reviews', [])
        questions = result.get('questions', [])
        total_reviews_raw = len(reviews_all)

        # Фильтрация отзывов по выбранным звёздам (вопросы НЕ фильтруются)
        reviews = filter_reviews_by_rating(reviews_all, filter_type)
        avg_rating = round(
            sum(r.get('rating', 0) for r in reviews) / len(reviews), 1
        ) if reviews else 0

        if not reviews and not questions:
            await status_msg.edit_text(
                "😔 Не удалось найти отзывы по этой ссылке.\n\n"
                "Возможные причины:\n• Товар ещё не имеет отзывов\n"
                "• Под выбранный фильтр ничего не попало\n• Маркетплейс изменил API"
            )
            db.add_request(user_id, marketplace, url, 0, success=False,
                           error_message="Отзывы не найдены", filter_type=filter_type)
            active_tasks.pop(user_id, None)
            return

        formatted_reviews = parser.format_reviews_for_excel(reviews) if reviews else []
        formatted_questions = parser.format_questions_for_excel(questions) if questions else []

        await status_msg.edit_text(
            f"📊 Найдено отзывов: {len(reviews)}\n"
            f"💬 Найдено вопросов: {len(questions)}\n"
            "⏳ Создаю Excel-файлы..."
        )

        files_to_send = []
        if formatted_reviews:
            fp = excel_exporter.export_reviews(formatted_reviews, marketplace)
            files_to_send.append(('reviews', fp, len(reviews)))
        if formatted_questions:
            fp = excel_exporter.export_reviews(formatted_questions, f"{marketplace}_Questions")
            files_to_send.append(('questions', fp, len(questions)))

        # Отправляем файлы и собираем file_id для /history
        reviews_file_id = None
        questions_file_id = None
        for file_type, filepath, count in files_to_send:
            file = FSInputFile(filepath)
            file_name = "отзывов" if file_type == 'reviews' else "вопросов"
            sent = await message.answer_document(
                file,
                caption=(f"✅ Готово!\n\n📊 Собрано {file_name}: {count}\n"
                         f"🏪 Маркетплейс: {marketplace}\n"
                         f"📅 Дата: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
            )
            if sent.document:
                if file_type == 'reviews':
                    reviews_file_id = sent.document.file_id
                else:
                    questions_file_id = sent.document.file_id

        # Сводка
        await status_msg.edit_text(
            "✅ <b>Готово!</b>\n\n"
            f"📦 Артикул: <code>{product_id}</code>\n"
            f"🔍 Фильтр: {filter_label(filter_type)}\n"
            f"⭐ Отзывов: <b>{len(reviews)}</b> (всего {total_reviews_raw} без фильтра)\n"
            f"❓ Вопросов: <b>{len(questions)}</b>\n"
            f"📊 Средний рейтинг: <b>{avg_rating}</b>",
            parse_mode="HTML",
        )

        db.add_request(
            user_id, marketplace, url, len(reviews), success=True,
            filter_type=filter_type, questions_count=len(questions),
            avg_rating=avg_rating, reviews_file_id=reviews_file_id,
            questions_file_id=questions_file_id,
        )

        for _, filepath, _ in files_to_send:
            if os.path.exists(filepath):
                os.remove(filepath)

    except ValueError as e:
        logger.error(f"Ошибка валидации: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)}")
        db.add_request(user_id, marketplace, url, 0, success=False,
                       error_message=str(e), filter_type=filter_type)
    except Exception as e:
        logger.error(f"Неожиданная ошибка при парсинге: {e}", exc_info=True)
        await status_msg.edit_text(
            f"❌ Произошла ошибка при парсинге:\n{str(e)}\n\n"
            "Попробуйте другую ссылку или обратитесь к администратору."
        )
        db.add_request(user_id, marketplace, url, 0, success=False,
                       error_message=str(e), filter_type=filter_type)
    finally:
        active_tasks.pop(user_id, None)
```

Также обновить импорт парсера вверху файла:
```python
from wb_parser_playwright import WildberriesParserPlaywright, filter_reviews_by_rating
```

- [ ] **Step 3: Проверить импортируемость**

Run: `BOT_TOKEN=dummy python -c "import bot"`
Expected: без ошибок.

- [ ] **Step 4: Коммит**

```bash
git add bot.py
git commit -m "refactor: handle_url показывает кнопки фильтра, сбор вынесен в run_collection"
```

---

## Task 6: Callback-обработчики фильтра

**Files:**
- Modify: `bot.py` (добавить callback-handlers после `run_collection`)

- [ ] **Step 1: Добавить обработчики**

После `run_collection` добавить:

```python
@dp.callback_query(F.data.startswith("flt:"), CollectStates.waiting_filter)
async def on_filter(callback: CallbackQuery, state: FSMContext):
    key = callback.data.split(":", 1)[1]
    data = await state.get_data()
    if not data.get('url'):
        await callback.message.edit_text("⚠️ Сессия устарела, отправьте ссылку заново.")
        await state.clear()
        await callback.answer()
        return

    if key == "custom":
        await state.update_data(custom_stars=[])
        await callback.message.edit_text(
            "🔢 <b>Выберите нужные оценки:</b>",
            reply_markup=build_star_keyboard(set()), parse_mode="HTML",
        )
        await callback.answer()
        return

    if key == "back":
        await state.update_data(custom_stars=[])
        await callback.message.edit_text(
            "Выберите фильтр для отзывов:", reply_markup=build_filter_keyboard()
        )
        await callback.answer()
        return

    if key == "done":
        stars = sorted(set(data.get('custom_stars', [])))
        if not stars:
            await callback.answer("❌ Выберите хотя бы одну оценку!", show_alert=True)
            return
        filter_type = ",".join(str(s) for s in stars)
    else:
        filter_type = key  # all / 1 / 1-2 / 1-3 / 4-5

    await state.update_data(filter=filter_type)
    data = await state.get_data()
    await callback.message.edit_text(f"⏳ Запускаю сбор (фильтр: {filter_label(filter_type)})...")
    await callback.answer()
    await state.clear()
    await run_collection(callback.message, callback.from_user.id, data)


@dp.callback_query(F.data.startswith("star:"), CollectStates.waiting_filter)
async def on_star_toggle(callback: CallbackQuery, state: FSMContext):
    star = int(callback.data.split(":", 1)[1])
    data = await state.get_data()
    stars = set(data.get('custom_stars', []))
    if star in stars:
        stars.discard(star)
    else:
        stars.add(star)
    await state.update_data(custom_stars=sorted(stars))
    await callback.message.edit_reply_markup(reply_markup=build_star_keyboard(stars))
    await callback.answer()
```

Примечание: `run_collection` получает `data` со снимком FSM (включая `filter`) до `state.clear()`, поэтому очистка состояния перед запуском сбора безопасна.

- [ ] **Step 2: Проверить импортируемость**

Run: `BOT_TOKEN=dummy python -c "import bot"`
Expected: без ошибок.

- [ ] **Step 3: Коммит**

```bash
git add bot.py
git commit -m "feat: callback-обработчики выбора фильтра и ручных звёзд"
```

---

## Task 7: Команда /history с повторной отправкой

**Files:**
- Modify: `bot.py` (новый handler + callback)

- [ ] **Step 1: Добавить /history и callback скачивания**

Добавить после обработчиков фильтра:

```python
@dp.message(Command("history"))
async def cmd_history(message: Message):
    user_id = message.from_user.id
    rows = db.get_recent_requests(user_id, limit=5)
    # только успешные запуски с файлами
    rows = [r for r in rows if r['success'] and r.get('reviews_file_id')]
    if not rows:
        await message.answer("📭 История пока пуста. Отправьте ссылку на товар, чтобы начать.")
        return

    builder = InlineKeyboardBuilder()
    lines = ["<b>📋 Последние запросы:</b>\n"]
    for i, r in enumerate(rows, 1):
        created = (r['created_at'] or "")[:16]
        lines.append(
            f"{i}. <b>{filter_label(r.get('filter_type'))}</b> | "
            f"Отзывов: {r['reviews_count']} | Вопросов: {r['questions_count']} | "
            f"Рейтинг: {r['avg_rating']}\n   📅 {created}"
        )
        builder.button(text=f"📥 Скачать #{i}", callback_data=f"dl:{r['id']}")
    builder.adjust(2)
    lines.append("\nНажмите кнопку, чтобы скачать файлы повторно.")
    await message.answer("\n".join(lines), reply_markup=builder.as_markup(), parse_mode="HTML")


@dp.callback_query(F.data.startswith("dl:"))
async def on_download(callback: CallbackQuery):
    req_id = int(callback.data.split(":", 1)[1])
    rows = db.get_recent_requests(callback.from_user.id, limit=50)
    row = next((r for r in rows if r['id'] == req_id), None)
    if not row or not row.get('reviews_file_id'):
        await callback.answer("Файлы не найдены.", show_alert=True)
        return
    await callback.message.answer("📦 Повторная отправка файлов:")
    try:
        await callback.message.answer_document(row['reviews_file_id'])
        if row.get('questions_file_id'):
            await callback.message.answer_document(row['questions_file_id'])
        await callback.answer("Файлы отправлены!")
    except Exception as e:
        logger.error(f"Не удалось переотправить файлы: {e}")
        await callback.answer("Файл недоступен, соберите заново.", show_alert=True)
```

- [ ] **Step 2: Проверить импортируемость**

Run: `BOT_TOKEN=dummy python -c "import bot"`
Expected: без ошибок.

- [ ] **Step 3: Коммит**

```bash
git add bot.py
git commit -m "feat: /history с повторной отправкой файлов по file_id"
```

---

## Task 8: Обновить /cancel и /help

**Files:**
- Modify: `bot.py` (`cmd_cancel` строки 124-141, `cmd_help` строки 108-122)

- [ ] **Step 1: Добавить очистку FSM в /cancel**

Заменить сигнатуру `cmd_cancel` (строка 125) — добавить `state: FSMContext`, и в начале тела вызвать `await state.clear()`:

```python
@dp.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    if user_id in active_tasks:
        active_tasks[user_id]['cancelled'] = True
        await message.answer("⛔ Отменяю текущую задачу...")
    else:
        await message.answer("ℹ️ Нет активных задач для отмены.")
```

(если текущее тело `cmd_cancel` отличается — сохранить его логику, добавив только `state: FSMContext` в сигнатуру и `await state.clear()` первой строкой)

- [ ] **Step 2: Обновить текст /help**

В `cmd_help` (строки 108-122) в текст справки добавить упоминание фильтра, артикула и /history. Дописать в строку с описанием команд:

```
"📋 <b>Команды:</b>\n"
"• Отправьте ссылку на товар <b>или артикул</b> (например <code>12345678</code>)\n"
"• После этого выберите фильтр отзывов по звёздам\n"
"• /history — последние 5 запусков с повторным скачиванием\n"
"• /cancel — отменить текущий сбор\n"
"• /stats — ваша статистика\n"
```

(встроить в существующий текст `cmd_help`, сохранив его стиль и `parse_mode`)

- [ ] **Step 3: Проверить импортируемость**

Run: `BOT_TOKEN=dummy python -c "import bot"`
Expected: без ошибок.

- [ ] **Step 4: Коммит**

```bash
git add bot.py
git commit -m "feat: /cancel чистит FSM, /help описывает фильтр/артикул/history"
```

---

## Task 9: Финальная проверка

- [ ] **Step 1: Прогнать весь тест-сьют**

Run: `pytest -v`
Expected: PASS — прежние 61 тест + новые (фильтр 9, артикул 5, БД 2).

- [ ] **Step 2: Проверить импорт бота**

Run: `BOT_TOKEN=dummy python -c "import bot; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Ручная проверка потока (если доступен реальный BOT_TOKEN)**

Запустить бота локально, в личке: отправить артикул `12345678` → должны появиться кнопки фильтра → выбрать «1–3★» → дождаться файлов и сводки → `/history` → «📥 Скачать #1» → файлы приходят повторно. Это ручной шаг; при отсутствии токена пропустить и отметить в отчёте.

- [ ] **Step 4: Финальный коммит (если остались несохранённые изменения)**

```bash
git add -A && git commit -m "test: финальная проверка фич фильтра/history/артикула" || echo "нечего коммитить"
```

---

## Self-Review (выполнено автором плана)

**Spec coverage:**
- Фильтр по звёздам (пресеты + ручной выбор) → Task 1, 4, 5, 6 ✓
- /history через file_id, последние 5, только успешные → Task 3, 7 ✓
- Приём чистого артикула → Task 2 ✓
- Сводка после сбора → Task 5 ✓
- Rate-limit на шаге фильтра → Task 5 (в `run_collection`) ✓
- Вопросы не фильтруются → Task 5 (фильтр применяется только к reviews) ✓
- FSM вместо dict → Task 4, 5, 6 ✓
- Сессия устарела / пустой state → Task 6 (`on_filter`) ✓
- /cancel чистит state → Task 8 ✓
- Группы игнорируются → сохранён `F.chat.type == "private"` в Task 5 ✓

**Расхождение со спеком (исправлено в плане):** спек предполагал правку `supabase_database.py` — файла нет в репо, изменения только в `database.py`. Зафиксировано в шапке плана.

**Type consistency:** `filter_reviews_by_rating(reviews, filter_type)` — одинаковая сигнатура в Task 1 и вызове Task 5. `filter_label()` определён в Task 4, используется в Task 5 и 7. `get_recent_requests` возвращает `id` (Task 3), используется в Task 7. `add_request` kwargs совпадают между Task 3 и вызовами Task 5. ✓

**Placeholder scan:** код приведён полностью в каждом шаге, плейсхолдеров нет. ✓
