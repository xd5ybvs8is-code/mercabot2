import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import Awaitable, Callable
from typing import Any, TYPE_CHECKING

from telegram.client import TelegramClient, TelegramRateLimitError, TelegramPermanentError

if TYPE_CHECKING:
    from metrics import MetricsCollector

logger = logging.getLogger(__name__)

# Файл, куда пишутся безвозвратно потерянные сообщения — чтобы админ
# мог посмотреть на сервере, даже когда Telegram недоступен.
_DROPS_LOG = Path(__file__).resolve().parent.parent / "dropped_messages.log"

# Минимальный адаптивный порог скорости отправки после 429.
MIN_RATE = 1
# Сколько успешных отправок подряд дают +1 к текущему rate (плавное восстановление).
RECOVERY_SUCCESSES = 10
# Таймаут ожидания опустошения очереди при закрытии (секунды).
DRAIN_TIMEOUT = 5.0

# Исходы _send_one.
_OK = 0           # сообщение ушло успешно
_RATE_LIMITED = 1 # 429 — сообщение возвращено в очередь, нужен retry_after
_FAILED = 2       # сеть/API недоступен — сообщение возвращено в очередь, retry в следующий tick
_DROPPED = 3      # превышен лимит попыток — сообщение удалено из очереди навсегда

# Сколько неудачных попыток отправки сообщения, прежде чем сдаться.
_MAX_ATTEMPTS = 20
# Durable-сообщения тоже не ретраим вечно — после этого порога сдаёмся.
_MAX_DURABLE_ATTEMPTS = 100


class Priority:
    """Приоритет сообщения в очереди. Меньше число = выше приоритет."""

    HIGH = 0      # ответы на команды / кнопки — уходят первыми
    NORMAL = 1    # уведомления о новых товарах + pending


@dataclass(order=True)
class OutgoingMessage:
    priority: int
    seq: int                                  # монотонный счётчик → FIFO внутри приоритета
    chat_id: str = field(compare=False)
    text: str = field(compare=False)
    disable_preview: bool = field(compare=False)
    show_keyboard: bool = field(compare=False)
    # Какую клавиатуру прикрепить: "main" (по умолчанию), "admin" (меню админ-панели),
    # "none" (без клавиатуры — для системных/разовых сообщений).
    keyboard_kind: str = field(default="main", compare=False)
    language: str = field(default="ru", compare=False)
    # Подсказка в поле ввода (input_field_placeholder в ReplyKeyboardMarkup).
    placeholder: str | None = field(default=None, compare=False)
    # Есть ли у чата активная подписка (влияет на текст кнопки в меню).
    is_subscribed: bool = field(default=False, compare=False)
    # Счётчик неудачных попыток отправки. После _MAX_ATTEMPTS сообщение дропается.
    attempts: int = field(default=0, compare=False)
    # Durable notification acknowledgement, called only after Telegram accepts it.
    on_success: Callable[[], Awaitable[None]] | None = field(default=None, compare=False)


class MessageSender:
    """Фоновый pump, выкачивающий очередь сообщений с дросселированием.

    Обходит два лимита Telegram:
      • глобальный — N сообщений в секунду (rate_per_sec из .env);
      • на один чат — не чаще чем chat_min_interval секунд (по умолчанию 1.0).

    При HTTP 429 засыпает на retry_after и адаптивно снижает скорость,
    после серии успешных отправок — плавно восстанавливает.
    """

    def __init__(
        self,
        client: TelegramClient,
        rate_per_sec: int,
        chat_min_interval: float = 1.0,
        admin_user_ids: frozenset[str] = frozenset(),
        on_chat_lost: Callable[[str], Awaitable[None]] | None = None,
        metrics: "MetricsCollector | None" = None,
    ) -> None:
        self._client = client
        self._target_rate = max(1, int(rate_per_sec))
        self._chat_min_interval = max(0.0, float(chat_min_interval))
        self._admin_user_ids = admin_user_ids
        self._on_chat_lost = on_chat_lost
        self._metrics = metrics
        self._queue: asyncio.PriorityQueue[OutgoingMessage] = asyncio.PriorityQueue()
        self._seq = 0
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        # Текущая (адаптивная) скорость. Стартуем с целевой.
        self._current_rate = self._target_rate
        self._success_streak = 0
        # timestamp последней отправки в каждый chat_id
        self._last_sent: dict[str, float] = {}

    # ── Lifecycle ────────────────────────────────────────────────

    def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._pump_loop(), name="tg-sender-pump")
        logger.info(
            "📤 MessageSender started (target_rate=%s/s, chat_interval=%ss)",
            self._target_rate, self._chat_min_interval,
        )

    async def stop(self) -> None:
        """Мягко останавливает pump: ждёт опустошения очереди, затем гасит задачу."""
        if self._task is None:
            return
        # Ждём, пока очередь не станет пустой, с таймаутом.
        try:
            await asyncio.wait_for(self._drain_empty(), timeout=DRAIN_TIMEOUT)
        except asyncio.TimeoutError:
            logger.warning(
                "⚠️ Sender drain timed out after %ss — %s message(s) still queued",
                DRAIN_TIMEOUT, self._queue.qsize(),
            )
        self._stop_event.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        logger.info("📤 MessageSender stopped")

    async def _drain_empty(self) -> None:
        while not self._queue.empty() and not self._stop_event.is_set():
            await asyncio.sleep(0.1)

    # ── Public API ───────────────────────────────────────────────

    def enqueue(
        self,
        chat_id: str,
        text: str,
        *,
        disable_preview: bool = True,
        show_keyboard: bool = True,
        priority: int = Priority.NORMAL,
        keyboard_kind: str = "main",
        language: str = "ru",
        placeholder: str | None = None,
        is_subscribed: bool = False,
        on_success: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        """Кладёт сообщение в очередь. Не блокирует.

        keyboard_kind:
          "main"  — основная клавиатура (с админ-кнопкой, если chat_id — админ);
          "admin" — клавиатура админ-панели (ADMIN_KEYBOARD);
          "none"  — без клавиатуры. При show_keyboard=False kind игнорируется.
        """
        self._seq += 1
        msg = OutgoingMessage(
            priority=priority,
            seq=self._seq,
            chat_id=chat_id,
            text=text,
            disable_preview=disable_preview,
            show_keyboard=show_keyboard,
            keyboard_kind=keyboard_kind,
            language=language,
            placeholder=placeholder,
            is_subscribed=is_subscribed,
            on_success=on_success,
        )
        self._queue.put_nowait(msg)
        if self._metrics is not None:
            asyncio.ensure_future(self._metrics.inc_counter("mercabot_notifications_queued_total"))
        logger.debug(
            "📨 Enqueued msg #%s (chat=%s, prio=%s, qsize=%s)",
            msg.seq, chat_id, priority, self._queue.qsize(),
        )

    def stats(self) -> dict[str, Any]:
        return {
            "queue_size": self._queue.qsize(),
            "current_rate": self._current_rate,
            "target_rate": self._target_rate,
        }

    # ── Pump ─────────────────────────────────────────────────────

    async def _pump_loop(self) -> None:
        """Один tick = 1 секунда; за tick — до current_rate отправок."""
        logger.info("📨 Sender pump loop started")
        try:
            while not self._stop_event.is_set():
                sent_this_tick = 0
                rate_limited = False
                deferred: list[OutgoingMessage] = []

                while sent_this_tick < self._current_rate and not self._stop_event.is_set():
                    try:
                        msg = self._queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break

                    if self._is_chat_throttled(msg.chat_id):
                        # В этот чат только что ушли — откладываем до следующего tick'а.
                        deferred.append(msg)
                        continue

                    outcome = await self._send_one(msg)
                    sent_this_tick += 1
                    if outcome == _RATE_LIMITED:
                        # Telegram попросил притормозить — рвём текущий tick,
                        # сообщение уже возвращено в очередь, остальное уйдёт
                        # следующим tick'ом после retry_after.
                        rate_limited = True
                        break
                    if outcome == _FAILED:
                        # Сеть/Telegram недоступны — сообщение уже в очереди.
                        # Дальше в этот tick лезть бессмысленно (та же ошибка),
                        # ждём до следующего tick'а и повторяем с сохранением порядка.
                        break
                    if outcome == _DROPPED:
                        # Сообщение удалено из очереди навсегда (превышен
                        # _MAX_ATTEMPTS). Просто переходим к следующему.
                        continue

                # Deferred возвращаем в очередь (с теми же priority/seq → FIFO сохраняется).
                for msg in deferred:
                    self._queue.put_nowait(msg)

                if sent_this_tick or deferred or self._queue.qsize():
                    logger.debug(
                        "tick: sent=%s deferred=%s qsize=%s rate=%s%s",
                        sent_this_tick, len(deferred), self._queue.qsize(),
                        self._current_rate, " [429]" if rate_limited else "",
                    )

                if self._metrics is not None:
                    await self._metrics.set_gauge(
                        "mercabot_sender_queue_size", float(self._queue.qsize()),
                    )
                    await self._metrics.set_gauge(
                        "mercabot_sender_current_rate", float(self._current_rate),
                    )

                # Sleep до следующей секунды, но реагируем на stop.
                # Если был 429 — retry_after уже отсипан внутри _send_one,
                # здесь просто ждём до следующего tick'а.
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=1.0)
                except asyncio.TimeoutError:
                    pass
        except asyncio.CancelledError:
            logger.info("📨 Sender pump cancelled")
            raise
        finally:
            logger.info("📨 Sender pump loop exited")

    def _is_chat_throttled(self, chat_id: str) -> bool:
        if self._chat_min_interval <= 0:
            return False
        last = self._last_sent.get(chat_id)
        if last is None:
            return False
        delta = asyncio.get_event_loop().time() - last
        return delta < self._chat_min_interval

    async def _send_one(self, msg: OutgoingMessage) -> int:
        """Отправляет одно сообщение.

        Возвращает один из _OK / _RATE_LIMITED / _FAILED.
        При _RATE_LIMITED и _FAILED сообщение уже возвращено в очередь.
        """
        payload: dict[str, Any] = {
            "chat_id": msg.chat_id,
            "text": msg.text,
            "parse_mode": "HTML",
            "disable_web_page_preview": msg.disable_preview,
        }
        if msg.show_keyboard:
            # Импорт здесь, чтобы избежать циклической зависимости sender↔bot.
            from telegram.keyboard import (
                build_keyboard_markup,
                build_admin_keyboard_markup,
                build_admin_whitelist_keyboard_markup,
                build_cancel_keyboard_markup,
                build_add_type_keyboard_markup,
                build_url_management_keyboard_markup,
            )

            if msg.keyboard_kind == "cancel":
                payload["reply_markup"] = build_cancel_keyboard_markup(
                    language=msg.language, placeholder=msg.placeholder,
                )
            elif msg.keyboard_kind == "add_type":
                payload["reply_markup"] = build_add_type_keyboard_markup(
                    language=msg.language, placeholder=msg.placeholder,
                )
            elif msg.keyboard_kind == "admin_whitelist":
                is_admin = msg.chat_id in self._admin_user_ids
                payload["reply_markup"] = (
                    build_admin_whitelist_keyboard_markup(language=msg.language, placeholder=msg.placeholder)
                    if is_admin
                    else build_keyboard_markup(False, language=msg.language, placeholder=msg.placeholder, is_subscribed=msg.is_subscribed)
                )
            elif msg.keyboard_kind == "admin":
                # Меню админ-панели — только для админа; на всякий случай
                # перепроверяем права, чтобы не показать админ-кнопки не-админу.
                is_admin = msg.chat_id in self._admin_user_ids
                payload["reply_markup"] = (
                    build_admin_keyboard_markup(language=msg.language, placeholder=msg.placeholder)
                    if is_admin
                    else build_keyboard_markup(False, language=msg.language, placeholder=msg.placeholder, is_subscribed=msg.is_subscribed)
                )
            elif msg.keyboard_kind == "url_management":
                payload["reply_markup"] = build_url_management_keyboard_markup(
                    language=msg.language, placeholder=msg.placeholder,
                )
            else:
                # Основная клавиатура: админ видит доп. ряд с входом в панель.
                is_admin = msg.chat_id in self._admin_user_ids
                payload["reply_markup"] = build_keyboard_markup(
                    is_admin, language=msg.language, placeholder=msg.placeholder,
                    is_subscribed=msg.is_subscribed,
                )

        try:
            ok = await self._client.call_api("sendMessage", payload)
        except TelegramPermanentError as exc:
            logger.error(
                "💀 Permanent error for chat %s: %s — dropping msg #%s",
                msg.chat_id, exc.description, msg.seq,
            )
            if self._on_chat_lost is not None:
                try:
                    await self._on_chat_lost(msg.chat_id)
                except Exception:
                    logger.exception("Failed to clean up lost chat %s", msg.chat_id)
            self._log_dropped_message(msg)
            if self._metrics is not None:
                await self._metrics.inc_counter("mercabot_notifications_failed_total")
            return _DROPPED
        except TelegramRateLimitError as exc:
            if self._metrics is not None:
                await self._metrics.inc_counter("mercabot_telegram_429_total")
            # Telegram просит притормозить: спим и снижаем скорость вдвое.
            self._success_streak = 0
            self._current_rate = max(MIN_RATE, self._current_rate // 2)
            logger.warning(
                "⚠️ 429 received — sleeping %ss, rate ↓ to %s/s, msg #%s requeued",
                exc.retry_after, self._current_rate, msg.seq,
            )
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=exc.retry_after)
            except asyncio.TimeoutError:
                pass
            self._queue.put_nowait(msg)
            return _RATE_LIMITED
        if not ok:
            # call_api пробовал MAX_RETRIES и вернул False — сеть недоступна
            # или Telegram отдаёт не-200/не-429.
            msg.attempts += 1
            if msg.attempts > _MAX_ATTEMPTS:
                if msg.on_success is not None:
                    if msg.attempts > _MAX_DURABLE_ATTEMPTS:
                        self._success_streak = 0
                        logger.error(
                            "💀 Durable msg #%s DROPPED after %s attempts (chat=%s)",
                            msg.seq, _MAX_DURABLE_ATTEMPTS, msg.chat_id,
                        )
                        self._log_dropped_message(msg)
                        if self._metrics is not None:
                            await self._metrics.inc_counter("mercabot_notifications_failed_total")
                        return _DROPPED
                    self._queue.put_nowait(msg)
                    logger.error(
                        "❌ Durable msg #%s still unavailable; retrying (attempt %s/%s)",
                        msg.seq, msg.attempts, _MAX_DURABLE_ATTEMPTS,
                    )
                    return _FAILED
                self._success_streak = 0
                logger.error(
                    "💀 Msg #%s DROPPED after %s failed attempts (chat=%s)",
                    msg.seq, _MAX_ATTEMPTS, msg.chat_id,
                )
                self._log_dropped_message(msg)
                if self._metrics is not None:
                    await self._metrics.inc_counter("mercabot_notifications_failed_total")
                return _DROPPED
            self._success_streak = 0
            logger.error(
                "❌ sendMessage failed — msg #%s (chat=%s) attempt %s/%s, requeued",
                msg.seq, msg.chat_id, msg.attempts, _MAX_ATTEMPTS,
            )
            self._queue.put_nowait(msg)
            return _FAILED
        # Успешная отправка — плавно восстанавливаем скорость.
        self._last_sent[msg.chat_id] = asyncio.get_event_loop().time()
        self._success_streak += 1
        if (
            self._success_streak >= RECOVERY_SUCCESSES
            and self._current_rate < self._target_rate
        ):
            self._current_rate = min(self._target_rate, self._current_rate + 1)
            self._success_streak = 0
            logger.info("📈 Sender rate recovered ↑ to %s/s", self._current_rate)
        if msg.on_success is not None:
            try:
                await msg.on_success()
            except Exception:
                # Telegram already accepted the message. Retrying can produce
                # a duplicate, but it prevents a DB acknowledgement failure
                # from leaving the durable outbox stuck forever.
                self._queue.put_nowait(msg)
                logger.exception("Failed to acknowledge delivered msg #%s", msg.seq)
                return _FAILED
        if self._metrics is not None:
            await self._metrics.inc_counter("mercabot_notifications_sent_total")
        return _OK

    def _log_dropped_message(self, msg: OutgoingMessage) -> None:
        """Записать потерянное сообщение в лог-файл на сервере."""
        preview = msg.text[:200]
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        entry = (
            f"[{ts}] Msg #{msg.seq} | chat={msg.chat_id} | "
            f"attempts={msg.attempts}\n"
            f"  {preview}\n"
        )
        try:
            with open(_DROPS_LOG, "a", encoding="utf-8") as f:
                f.write(entry)
        except OSError:
            logger.exception("Failed to write dropped message to %s", _DROPS_LOG)
