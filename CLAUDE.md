# CLAUDE.md — Контекст для ИИ-ассистента

Этот файл описывает архитектуру, ключевые решения и соглашения проекта. Читается автоматически при старте сессии.

---

## Что это за проект

Telegram-бот **ParserReview** — парсер отзывов и вопросов с Wildberries.

Пользователь отправляет ссылку на товар → бот открывает страницу в headless Chromium через Playwright, перехватывает ответы WB API, извлекает отзывы/вопросы, анализирует тональность, генерирует Excel-файл и отправляет его обратно в Telegram.

Язык: **Python 3.11**. Интерфейс бота и комментарии в коде — **русский**.

---

## Ключевые файлы

| Файл | Назначение |
|------|-----------|
| `bot.py` | Точка входа. Обработчики команд и URL, FSM-состояния, отправка файлов |
| `wb_parser_playwright.py` | Ядро парсера: Playwright, перехват сетевых ответов, DOM-fallback |
| `excel_exporter.py` | Генерация Excel: форматирование, цвета, диаграммы |
| `sentiment_analyzer.py` | Словарный анализ тональности на русском |
| `url_validator.py` | Валидация и санитизация URL (WB / Ozon) |
| `database.py` | SQLite-реализация слоя данных |
| `supabase_database.py` | Supabase-реализация (тот же интерфейс, что и `database.py`) |
| `config.py` | Загрузка `.env`, типизация, дефолты |
| `exceptions.py` | Иерархия кастомных исключений |

---

## Архитектурные решения

### Двойная база данных
`database.py` (SQLite) и `supabase_database.py` реализуют **идентичный интерфейс**. Переключение — через `Config.use_supabase()`, который проверяет наличие `SUPABASE_URL` и `SUPABASE_KEY` в окружении. Локально — SQLite, на Railway — Supabase (потому что Railway не даёт персистентного диска).

### Перехват API вместо прямых запросов
Парсер не ломится напрямую к WB API. Вместо этого открывает реальную страницу и перехватывает network-ответы через Playwright. Это обходит большинство защит. При неудаче — DOM-fallback через BeautifulSoup.

### Retry с экспоненциальным backoff
`tenacity` оборачивает основные операции парсинга. Повторяет при `NetworkError`, `TimeoutError`, `BrowserError`. Настраивается в `.env` через `RETRY_*` переменные.

### Rate limiting
Хранится в таблице `rate_limits` (timestamp per user). При каждом запросе считается кол-во записей за последние `RATE_LIMIT_HOURS` часов. Записи старше 24 часов автоматически удаляются.

---

## Соглашения по коду

- **Async везде**: aiogram 3 + aiohttp + async Playwright
- **Логирование**: `logging.getLogger(__name__)` в каждом модуле. RotatingFileHandler → `bot.log` (10 МБ, 5 копий)
- **Исключения**: кидать типизированные классы из `exceptions.py`, не голые `Exception`
- **Конфиг**: всё через `Config` из `config.py`, не обращаться к `os.environ` напрямую
- **Excel**: санитизировать значения ячеек (экранировать `=`, `+`, `-`, `@`) чтобы избежать formula injection
- **SQL**: только параметризованные запросы — `?` placeholders

---

## Что НЕ реализовано (но готов фундамент)

- **Парсер Ozon**: `url_validator.py` распознаёт ozon.ru, но `OzonParser` не написан
- **Очередь задач**: нет Celery/Redis, задачи обрабатываются синхронно в handler'е
- **Авторизация**: безопасность — только Telegram bot token + проверка подписки на канал

---

## Среда выполнения

```
BOT_TOKEN          — обязательный, токен @BotFather
ADMIN_IDS          — список int через запятую
REQUIRED_CHANNEL   — @username канала для проверки подписки
RATE_LIMIT_REQUESTS / RATE_LIMIT_HOURS — лимиты
MAX_REVIEWS / MAX_QUESTIONS — лимиты парсинга
PARSER_TIMEOUT     — мс (default 60000)
PARSER_HEADLESS    — True/False
SUPABASE_URL / SUPABASE_KEY — если нужен облачный режим
```

---

## Тесты

```bash
pytest                          # запуск всех тестов
pytest --cov=. --cov-report=html  # с покрытием
```

Три файла в `tests/`:
- `test_url_validator.py` — 30 тестов
- `test_sentiment_analyzer.py` — 17 тестов
- `test_database.py` — 14 тестов

---

## Деплой

**Локально:**
```bash
pip install -r requirements.txt
playwright install chromium --with-deps
python bot.py
```

**Docker:**
```bash
docker-compose up -d
```

**Railway:** `RAILWAY_DEPLOY.md` — пошаговая инструкция. Важно: указать Supabase, иначе данные не сохранятся.

---

## Типичные задачи и где что менять

| Задача | Файл |
|--------|------|
| Добавить команду бота | `bot.py` — новый handler + регистрация в `dp` |
| Изменить логику парсинга | `wb_parser_playwright.py` |
| Добавить поля в Excel | `excel_exporter.py` |
| Добавить слова тональности | `sentiment_analyzer.py` — словари `POSITIVE_WORDS` / `NEGATIVE_WORDS` |
| Добавить поддержку нового маркетплейса | `url_validator.py` + новый `*_parser.py` |
| Изменить схему БД | `database.py` + `supabase_database.py` (оба!) |
| Добавить env-переменную | `config.py` + `.env.example` |
