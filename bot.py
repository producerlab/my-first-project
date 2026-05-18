import asyncio
import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

from wb_parser_playwright import WildberriesParserPlaywright
from excel_exporter import ExcelExporter
from config import Config
from url_validator import URLValidator
from exceptions import InvalidURLError


# Настройка логирования с ротацией (макс 10MB, 5 бэкапов)
file_handler = RotatingFileHandler(
    'bot.log',
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5,
    encoding='utf-8'
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        file_handler,
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Загружаем переменные окружения
load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')

if not BOT_TOKEN:
    raise ValueError("Не найден BOT_TOKEN в .env файле!")

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ─── Подключение Telegram-алертов ошибок (ERROR/CRITICAL → группа Tech Alerts) ─
try:
    from alerting import set_bot as _alert_set_bot, setup_alerting as _alert_setup
    _alert_set_bot(bot)
    _alert_setup()
except Exception as _alert_err:
    logger.warning(f"alerting init failed: {_alert_err}")
# ─────────────────────────────────────────────────────────────────────────────

# Инициализация парсера и экспортера
wb_parser = WildberriesParserPlaywright(max_reviews=Config.MAX_REVIEWS)
excel_exporter = ExcelExporter()

from database import Database
db = Database()
logger.info("Используется локальная SQLite база данных")

# Настройки из Config (загружаются из .env)
RATE_LIMIT_REQUESTS = Config.RATE_LIMIT_REQUESTS
RATE_LIMIT_HOURS = Config.RATE_LIMIT_HOURS
REQUIRED_CHANNEL = Config.REQUIRED_CHANNEL
ADMIN_IDS = Config.ADMIN_IDS

# Словарь для отслеживания активных задач парсинга
active_tasks = {}


async def check_subscription(user_id: int) -> bool:
    """Проверяет подписку пользователя на канал"""
    try:
        member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
        # Статусы: creator, administrator, member - подписан
        # left, kicked - не подписан
        return member.status in ['creator', 'administrator', 'member']
    except Exception as e:
        logger.error(f"Ошибка проверки подписки: {e}")
        return False


@dp.message(Command("start"))
async def cmd_start(message: Message):
    """Обработчик команды /start"""
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name

    # Сохраняем пользователя в БД
    db.add_or_update_user(user_id, username, first_name, last_name)

    logger.info(f"Пользователь {user_id} ({username}) запустил бота")

    await message.answer(
        "👋 Привет!\n\n"
        "📝 Отправь ссылку на товар с Wildberries\n\n"
        "Я соберу все отзывы и отправлю тебе Excel-файл 📊"
    )


@dp.message(Command("help"))
async def cmd_help(message: Message):
    """Обработчик команды /help"""
    await message.answer(
        "📚 Инструкция:\n\n"
        f"1. ⚠️ Подпишись на канал: {REQUIRED_CHANNEL}\n"
        "2. Скопируй ссылку на товар с Wildberries\n"
        "3. Отправь мне ссылку\n"
        "4. Получи Excel-файлы с отзывами и вопросами\n\n"
        "📊 Что будет в файлах:\n"
        "• Отзывы: текст, рейтинг, дата, автор, плюсы, минусы\n"
        "• Вопросы: вопрос, ответ, дата, автор\n\n"
        f"⚡ Лимит: {RATE_LIMIT_REQUESTS} запросов в час"
    )


@dp.message(Command("cancel"))
async def cmd_cancel(message: Message):
    """Отменяет текущий парсинг"""
    user_id = message.from_user.id

    if user_id in active_tasks:
        active_tasks[user_id]['cancelled'] = True
        logger.info(f"Пользователь {user_id} отменил парсинг")
        await message.answer(
            "⛔ Парсинг отменён!\n\n"
            "Отправьте новую ссылку, когда будете готовы."
        )
    else:
        await message.answer(
            "❌ У вас нет активных задач парсинга.\n\n"
            "Отправьте ссылку на товар, чтобы начать."
        )


@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    """Показывает статистику пользователя"""
    user_id = message.from_user.id
    stats = db.get_user_stats(user_id)

    if stats['total_requests'] == 0:
        await message.answer(
            "📊 Ваша статистика:\n\n"
            "У вас пока нет запросов. Отправьте ссылку на товар, чтобы начать!"
        )
        return

    recent = db.get_recent_requests(user_id, limit=5)

    stats_text = f"📊 Ваша статистика:\n\n"
    stats_text += f"🔢 Всего запросов: {stats['total_requests']}\n"
    stats_text += f"📅 Первое использование: {stats['first_seen'][:10]}\n\n"

    if recent:
        stats_text += "📝 Последние запросы:\n"
        for req in recent:
            success_icon = "✅" if req['success'] else "❌"
            stats_text += f"{success_icon} {req['marketplace']} - {req['reviews_count']} отзывов ({req['created_at'][:10]})\n"

    await message.answer(stats_text)


@dp.message(Command("admin_stats"))
async def cmd_admin_stats(message: Message):
    """Показывает общую статистику бота (только для админов)"""
    user_id = message.from_user.id

    if user_id not in ADMIN_IDS:
        await message.answer("❌ У вас нет доступа к этой команде")
        return

    stats = db.get_total_stats()

    stats_text = "📊 Статистика бота:\n\n"
    stats_text += f"👥 Всего пользователей: {stats['total_users']}\n"
    stats_text += f"📝 Всего запросов: {stats['total_requests']}\n"
    stats_text += f"✅ Успешных запросов: {stats['successful_requests']}\n"
    stats_text += f"💬 Всего собрано отзывов: {stats['total_reviews']}\n\n"

    success_rate = (stats['successful_requests'] / stats['total_requests'] * 100) if stats['total_requests'] > 0 else 0
    stats_text += f"📈 Success rate: {success_rate:.1f}%"

    await message.answer(stats_text)
    logger.info(f"Админ {user_id} запросил статистику бота")


@dp.message(Command("admin_broadcast"))
async def cmd_admin_broadcast(message: Message):
    """Рассылка сообщения всем пользователям (только для админов)"""
    user_id = message.from_user.id

    if user_id not in ADMIN_IDS:
        await message.answer("❌ У вас нет доступа к этой команде")
        return

    # Получаем текст сообщения (после команды)
    text = message.text.replace('/admin_broadcast', '').strip()

    if not text:
        await message.answer(
            "📢 Формат команды:\n"
            "/admin_broadcast текст сообщения\n\n"
            "Это сообщение будет отправлено ВСЕМ пользователям бота!"
        )
        return

    # Получаем всех пользователей
    users = [(uid,) for uid in db.get_all_user_ids()]

    # Отправляем сообщение всем
    sent = 0
    failed = 0

    status_msg = await message.answer(f"📤 Начинаю рассылку {len(users)} пользователям...")

    for (uid,) in users:
        try:
            await bot.send_message(uid, text)
            sent += 1
            await asyncio.sleep(0.05)  # Небольшая задержка чтобы не словить лимит Telegram
        except Exception as e:
            failed += 1
            logger.error(f"Ошибка отправки сообщения пользователю {uid}: {e}")

    await status_msg.edit_text(
        f"✅ Рассылка завершена!\n\n"
        f"📤 Отправлено: {sent}\n"
        f"❌ Ошибок: {failed}"
    )

    logger.info(f"Админ {user_id} сделал рассылку: отправлено={sent}, ошибок={failed}")


@dp.message(Command("test_alert"))
async def cmd_test_alert(message: Message):
    """Тестирование Telegram-алертов (только для админов). Удалить после проверки."""
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        raise ValueError("alerting test from /test_alert command")
    except ValueError:
        logging.exception("проверка алертов")
    await message.answer("Тестовый алерт отправлен — проверь группу Tech Alerts")


@dp.message(F.text)
async def handle_url(message: Message):
    """Обработчик URL товара"""
    user_id = message.from_user.id
    username = message.from_user.username or "Unknown"
    url = message.text.strip()

    # Сохраняем/обновляем пользователя
    db.add_or_update_user(
        user_id,
        message.from_user.username,
        message.from_user.first_name,
        message.from_user.last_name
    )

    logger.info(f"Пользователь {user_id} ({username}) отправил URL: {url}")

    # Валидация URL через URLValidator
    try:
        sanitized_url = URLValidator.sanitize_url(url)
        marketplace_code, product_id = URLValidator.validate_url(sanitized_url)
        url = sanitized_url  # Используем очищенный URL
    except InvalidURLError as e:
        logger.warning(f"Невалидный URL от {user_id}: {e}")
        await message.answer(
            f"❌ {e.reason}\n\n"
            "Используйте /help для получения инструкций."
        )
        return

    # Проверяем что это Wildberries (пока только его поддерживаем)
    if marketplace_code != 'wildberries':
        logger.warning(f"Неподдерживаемый маркетплейс: {marketplace_code}")
        await message.answer(
            "❌ Пока поддерживается только Wildberries.\n\n"
            "Поддержка Ozon скоро появится!"
        )
        return

    marketplace = 'Wildberries'
    parser = wb_parser

    # Проверяем подписку на канал
    is_subscribed = await check_subscription(user_id)
    if not is_subscribed:
        logger.warning(f"Пользователь {user_id} не подписан на канал")
        await message.answer(
            "❌ Для использования бота необходимо подписаться на наш канал!\n\n"
            f"📢 Канал: {REQUIRED_CHANNEL}\n"
            f"🔗 Ссылка: https://t.me/khosnullin_channel\n\n"
            "После подписки отправьте ссылку снова."
        )
        return

    # Проверяем rate limit
    can_request, remaining = db.check_rate_limit(user_id, RATE_LIMIT_REQUESTS, RATE_LIMIT_HOURS)

    if not can_request:
        logger.warning(f"Пользователь {user_id} превысил лимит запросов")
        await message.answer(
            f"⛔ Вы превысили лимит запросов!\n\n"
            f"Доступно: {RATE_LIMIT_REQUESTS} запросов в {RATE_LIMIT_HOURS} час.\n"
            f"Пожалуйста, подождите немного и попробуйте снова."
        )
        return

    # Добавляем запись о rate limit
    db.add_rate_limit_record(user_id)

    # Отмечаем задачу как активную
    active_tasks[user_id] = {'cancelled': False, 'marketplace': marketplace}

    # Уведомляем пользователя о начале парсинга
    status_msg = await message.answer(
        f"⏳ Начинаю сбор отзывов с {marketplace}...\n"
        f"Осталось запросов: {remaining - 1}/{RATE_LIMIT_REQUESTS}\n\n"
        f"Для отмены используйте /cancel"
    )

    # Колбэк для обновления прогресса
    async def update_progress(current: int, total: int):
        try:
            if total > 0:
                percentage = (current / total) * 100
                bar_length = 20
                filled = int(bar_length * current / total)
                bar = '█' * filled + '░' * (bar_length - filled)

                await status_msg.edit_text(
                    f"⏳ Собираю отзывы с {marketplace}...\n\n"
                    f"📊 Прогресс: {current}/{total} ({percentage:.1f}%)\n"
                    f"{bar}"
                )
        except Exception as e:
            logger.error(f"Ошибка обновления прогресса: {e}")

    try:
        logger.info(f"Начало парсинга {marketplace} для пользователя {user_id}")

        # Парсим отзывы (и вопросы для WB)
        result = await parser.get_reviews(url, progress_callback=update_progress)

        # Проверяем, была ли отменена задача
        if user_id in active_tasks and active_tasks[user_id]['cancelled']:
            logger.info(f"Парсинг отменён пользователем {user_id}")
            await status_msg.edit_text("⛔ Парсинг отменён")
            del active_tasks[user_id]
            return

        # Результат - dict с reviews и questions
        reviews = result.get('reviews', [])
        questions = result.get('questions', [])

        if not reviews and not questions:
            logger.warning(f"Не найдено отзывов и вопросов: {url}")
            await status_msg.edit_text(
                f"😔 Не удалось найти отзывы по этой ссылке.\n\n"
                "Возможные причины:\n"
                "• Товар ещё не имеет отзывов\n"
                "• Неверная ссылка\n"
                "• Маркетплейс изменил API"
            )
            db.add_request(user_id, marketplace, url, 0, success=False,
                          error_message="Отзывы не найдены")
            return

        # Форматируем для Excel
        formatted_reviews = parser.format_reviews_for_excel(reviews) if reviews else []
        formatted_questions = parser.format_questions_for_excel(questions) if questions and hasattr(parser, 'format_questions_for_excel') else []

        # Debug логирование
        logger.info(f"DEBUG: questions count={len(questions)}, formatted_questions count={len(formatted_questions)}")
        if questions:
            logger.info(f"DEBUG: First question sample: {questions[0] if questions else 'None'}")

        # Создаем Excel файлы
        progress_text = f"📊 Найдено отзывов: {len(reviews)}\n"
        if questions and len(questions) > 0:
            progress_text += f"💬 Найдено вопросов: {len(questions)}\n"
        progress_text += "⏳ Создаю Excel-файлы..."

        await status_msg.edit_text(progress_text)

        files_to_send = []

        # Создаём файл с отзывами
        if formatted_reviews:
            reviews_filepath = excel_exporter.export_reviews(
                formatted_reviews,
                marketplace
            )
            logger.info(f"Создан файл отзывов: {reviews_filepath} ({len(reviews)} отзывов)")
            files_to_send.append(('reviews', reviews_filepath, len(reviews)))

        # Создаём файл с вопросами (только для WB, и только если они есть)
        if formatted_questions and len(formatted_questions) > 0:
            questions_filepath = excel_exporter.export_reviews(
                formatted_questions,
                f"{marketplace}_Questions"
            )
            logger.info(f"Создан файл вопросов: {questions_filepath} ({len(questions)} вопросов)")
            files_to_send.append(('questions', questions_filepath, len(questions)))

        # Отправляем файлы пользователю
        for file_type, filepath, count in files_to_send:
            file = FSInputFile(filepath)
            file_name = "отзывов" if file_type == 'reviews' else "вопросов"
            await message.answer_document(
                file,
                caption=f"✅ Готово!\n\n"
                        f"📊 Собрано {file_name}: {count}\n"
                        f"🏪 Маркетплейс: {marketplace}\n"
                        f"📅 Дата: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            )

        await status_msg.delete()

        # Сохраняем успешный запрос в БД
        total_items = len(reviews) + len(questions)
        db.add_request(user_id, marketplace, url, total_items, success=True)

        logger.info(f"Успешно отправлены файлы пользователю {user_id}")

        # Удаляем временные файлы
        for _, filepath, _ in files_to_send:
            if os.path.exists(filepath):
                os.remove(filepath)

    except ValueError as e:
        logger.error(f"Ошибка валидации: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)}")
        db.add_request(user_id, marketplace, url, 0, success=False,
                      error_message=str(e))
    except Exception as e:
        logger.error(f"Неожиданная ошибка при парсинге: {e}", exc_info=True)
        await status_msg.edit_text(
            f"❌ Произошла ошибка при парсинге:\n{str(e)}\n\n"
            "Попробуйте другую ссылку или обратитесь к администратору."
        )
        db.add_request(user_id, marketplace, url, 0, success=False,
                      error_message=str(e))
    finally:
        # Очищаем активную задачу
        if user_id in active_tasks:
            del active_tasks[user_id]


async def main():
    """Основная функция запуска бота"""
    # Очистка старых записей rate limit при старте
    db.cleanup_old_rate_limits(hours=24)
    logger.info("Очищены старые записи rate limit")

    logger.info("=" * 50)
    logger.info("Бот запущен и готов к работе!")
    logger.info(f"Лимит отзывов: {wb_parser.max_reviews}")
    logger.info(f"Лимит вопросов: {wb_parser.max_questions}")
    logger.info(f"Rate limit: {RATE_LIMIT_REQUESTS} запросов в {RATE_LIMIT_HOURS} час")
    logger.info("=" * 50)

    await dp.start_polling(bot)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
        print("\n❌ Бот остановлен")
