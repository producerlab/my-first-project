"""Telegram-алерты ошибок: ERROR/CRITICAL → группа Tech Alerts → тема проекта.

Setup:
    from alerting import setup_alerting, set_bot
    set_bot(bot)              # после создания инстанса aiogram Bot
    setup_alerting()          # в startup, один раз

Env-переменные (.env):
    REPORT_CHAT_ID=-100...    # ID группы алертов
    REPORT_THREAD_ID=...      # ID темы проекта (опционально)
    PROJECT_NAME=myproject    # префикс в шапке алерта (опционально)
"""
from __future__ import annotations

import asyncio
import html
import logging
import os
import time
import traceback
from datetime import datetime, timezone, timedelta
from typing import Optional

from cachetools import TTLCache

# ─── Конфигурация ─────────────────────────────────────────────────────────────

REPORT_CHAT_ID: Optional[int] = int(os.getenv("REPORT_CHAT_ID")) if os.getenv("REPORT_CHAT_ID") else None
REPORT_THREAD_ID: Optional[int] = int(os.getenv("REPORT_THREAD_ID")) if os.getenv("REPORT_THREAD_ID") else None
PROJECT_NAME: str = os.getenv("PROJECT_NAME", "")

DEDUP_TTL_SECONDS = 600
DEDUP_MAX_KEYS = 512
RATE_LIMIT_PER_HOUR = 20

SUPPRESS_PATTERNS = (
    "message is not modified",
    "message to delete not found",
    "message to edit not found",
    "query is too old",
    "bot was blocked by the user",
    "user is deactivated",
    "chat not found",
)

# Самовосстанавливающиеся сбои long-polling. Алертим только если повторяются
# подряд (см. THROTTLE_THRESHOLD), иначе шум.
THROTTLE_PATTERNS = (
    "failed to fetch updates",
    "telegramnetworkerror",
    "telegramconflicterror",
    "connection reset by peer",
    "server disconnected",
    "clientconnectorerror",
)
THROTTLE_WINDOW_SECONDS = 300  # 5 минут
THROTTLE_THRESHOLD = 5         # алертим только начиная с N-й ошибки в окне

MSK = timezone(timedelta(hours=3))

# ─── Состояние ────────────────────────────────────────────────────────────────

_bot = None
_dedup_cache: TTLCache = TTLCache(maxsize=DEDUP_MAX_KEYS, ttl=DEDUP_TTL_SECONDS)
_hour_bucket_start: float = 0.0
_hour_bucket_count: int = 0
_suppressed_notified: bool = False
_throttle_events: list[float] = []


def set_bot(bot) -> None:
    """Передать инстанс aiogram Bot для отправки алертов."""
    global _bot
    _bot = bot


def _rate_limit_check() -> tuple[bool, bool]:
    global _hour_bucket_start, _hour_bucket_count, _suppressed_notified
    now = time.monotonic()
    if now - _hour_bucket_start >= 3600:
        _hour_bucket_start = now
        _hour_bucket_count = 0
        _suppressed_notified = False
    if _hour_bucket_count < RATE_LIMIT_PER_HOUR:
        _hour_bucket_count += 1
        return True, False
    if not _suppressed_notified:
        _suppressed_notified = True
        return False, True
    return False, False


def _format_message(record: logging.LogRecord) -> str:
    ts = datetime.now(MSK).strftime("%H:%M МСК")
    level = record.levelname
    location = f"{record.module}.py:{record.lineno}"
    exc_text = ""
    if record.exc_info:
        exc_type, exc_value, _tb = record.exc_info
        type_name = exc_type.__name__ if exc_type else "Exception"
        exc_text = f"\n<b>{html.escape(type_name)}:</b> <code>{html.escape(str(exc_value)[:300])}</code>"
        tb_lines = traceback.format_exception(exc_type, exc_value, _tb)
        tb_text = "".join(tb_lines)
        if len(tb_text) > 1200:
            tb_text = "...\n" + tb_text[-1200:]
        exc_text += f"\n\n<pre>{html.escape(tb_text)}</pre>"
    msg = html.escape(str(record.getMessage())[:500])
    prefix = f"[{html.escape(PROJECT_NAME)}] " if PROJECT_NAME else ""
    return (
        f"🚨 {prefix}<b>{level}</b> · {ts}\n"
        f"<code>{html.escape(location)}</code>\n\n"
        f"{msg}{exc_text}"
    )


def _signature(record: logging.LogRecord) -> str:
    exc_type = ""
    if record.exc_info and record.exc_info[0]:
        exc_type = record.exc_info[0].__name__
    return f"{record.module}:{record.lineno}:{exc_type}"


def _is_suppressed(text: str) -> bool:
    lower = text.lower()
    return any(p in lower for p in SUPPRESS_PATTERNS)


def _is_throttled(text: str) -> bool:
    """True если это самовосстанавливающаяся ошибка и она ещё не накопилась до порога."""
    lower = text.lower()
    if not any(p in lower for p in THROTTLE_PATTERNS):
        return False
    now = time.monotonic()
    # Чистим старые события
    cutoff = now - THROTTLE_WINDOW_SECONDS
    while _throttle_events and _throttle_events[0] < cutoff:
        _throttle_events.pop(0)
    _throttle_events.append(now)
    # Алертим только если достигли порога серии
    return len(_throttle_events) < THROTTLE_THRESHOLD


class TelegramAlertHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if record.name.startswith("alerting"):
                return
            full_text = record.getMessage()
            if record.exc_info and record.exc_info[1]:
                full_text += " " + str(record.exc_info[1])
            if _is_suppressed(full_text):
                return
            if _is_throttled(full_text):
                return
            sig = _signature(record)
            if sig in _dedup_cache:
                return
            _dedup_cache[sig] = True
            allowed, need_notice = _rate_limit_check()
            if not allowed:
                if need_notice:
                    self._schedule(f"⚠️ Слишком много ошибок (>{RATE_LIMIT_PER_HOUR}/час) — алерты подавлены до следующего часа.")
                return
            self._schedule(_format_message(record))
        except Exception:
            import sys
            print("[alerting] emit failed", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)

    def _schedule(self, text: str) -> None:
        if _bot is None or not REPORT_CHAT_ID:
            return
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            return
        if not loop.is_running():
            return
        loop.create_task(self._send(text))

    async def _send(self, text: str) -> None:
        try:
            kwargs = dict(
                chat_id=REPORT_CHAT_ID,
                text=text,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            if REPORT_THREAD_ID is not None:
                kwargs["message_thread_id"] = REPORT_THREAD_ID
            await _bot.send_message(**kwargs)
        except Exception:
            import sys
            print("[alerting] send_message failed", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)


def setup_alerting() -> None:
    if not REPORT_CHAT_ID:
        logging.warning("alerting: REPORT_CHAT_ID не задан — отключено")
        return
    if _bot is None:
        logging.warning("alerting: bot не передан через set_bot() — отключено")
        return
    handler = TelegramAlertHandler()
    logging.getLogger().addHandler(handler)
    loop = asyncio.get_event_loop()
    loop.set_exception_handler(_asyncio_exception_handler)
    logging.info(
        "alerting: подключён → chat_id=%s thread_id=%s project=%s",
        REPORT_CHAT_ID, REPORT_THREAD_ID, PROJECT_NAME or "(не задан)",
    )


def _asyncio_exception_handler(loop, context: dict) -> None:
    msg = context.get("message", "asyncio unhandled exception")
    exc = context.get("exception")
    if exc:
        logging.error(msg, exc_info=(type(exc), exc, exc.__traceback__))
    else:
        logging.error("asyncio: %s", msg)
