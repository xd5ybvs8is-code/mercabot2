import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from typing import TYPE_CHECKING

from telegram.client import TelegramClient
from telegram.keyboard import (
    BUTTON_ACTIONS,
    ADMIN_BUTTON_ACTIONS,
    build_remove_inline_keyboard,
    build_confirm_delete_keyboard,
    build_list_items_inline_keyboard,
    build_url_detail_keyboard,
    build_rename_inline_keyboard,
)
from telegram.messages import format_item_notification, format_url_detail, format_url_list
from telegram.sender import MessageSender, Priority
from models.item import Item

if TYPE_CHECKING:
    from storage.urls import UrlStorage

logger = logging.getLogger(__name__)

POLL_INTERVAL = 2.0

# Handler type: (argument, chat_id, user_id) -> response text (async).
# user_id — Telegram account id отправителя (message.from.id), нужен для
# проверки прав администратора в админ-командах.
CommandHandler = Callable[[str, str, str], Awaitable[str]]


class TelegramNotifier:
    """High-level bot: message sending, command polling, button routing."""

    def __init__(
        self,
        token: str,
        rate_per_sec: int = 20,
        chat_min_interval: float = 1.0,
        admin_user_ids: frozenset[str] = frozenset(),
        url_storage: "UrlStorage | None" = None,
    ) -> None:
        self._client = TelegramClient(token)
        self._admin_user_ids = admin_user_ids
        self._url_storage = url_storage
        self._sender = MessageSender(
            self._client,
            rate_per_sec=rate_per_sec,
            chat_min_interval=chat_min_interval,
            admin_user_ids=admin_user_ids,
        )
        self._offset: int | None = None
        self._command_handlers: dict[str, CommandHandler] = {}
        # Ожидание ввода:
        #   {"phase": "add_name"} — ждём имя нового поиска
        #   {"phase": "add_url", "name": "..."} — ждём URL
        #   {"phase": "broadcast"} — ждём текст рассылки (только для админа)
        self._awaiting: dict[str, dict[str, str]] = {}
        # message_id последнего inline-сообщения для editMessageText (по chat_id)
        self._inline_msg_ids: dict[str, int] = {}

    async def start(self) -> None:
        logger.info("⏳ Starting Telegram bot...")
        await self._client.start()
        self._sender.start()
        logger.info("✅ Telegram bot started (long-polling mode)")

    async def close(self) -> None:
        logger.info("⏳ Closing Telegram bot...")
        # Сначала дренажируем очередь отправки, потом гасим клиент.
        await self._sender.stop()
        await self._client.close()
        logger.info("✅ Telegram bot closed")

    def register_commands(self, handlers: dict[str, CommandHandler]) -> None:
        self._command_handlers.update(handlers)

    # ── Sending messages ─────────────────────────────────────────
    #
    # Все отправки идут через единую очередь MessageSender, которая дросселирует
    # поток по глобальному rate-limit (msg/sec) и per-chat spacing (1 msg/sec на
    # чат), адаптивно снижая скорость при 429. send_message используется для
    # ответов на команды/кнопки — приоритет HIGH (уходят первыми).
    # send_item — уведомления о новых товарах, приоритет NORMAL.

    async def send_message(
        self,
        chat_id: str,
        text: str,
        disable_preview: bool = True,
        show_keyboard: bool = True,
        keyboard_kind: str = "main",
        placeholder: str | None = None,
    ) -> bool:
        self._sender.enqueue(
            chat_id,
            text,
            disable_preview=disable_preview,
            show_keyboard=show_keyboard,
            priority=Priority.HIGH,
            keyboard_kind=keyboard_kind,
            placeholder=placeholder,
        )
        return True

    async def send_item(self, chat_id: str, item: Item, search_name: str = "") -> bool:
        self._sender.enqueue(
            chat_id,
            format_item_notification(item, search_name),
            disable_preview=False,
            show_keyboard=False,
            priority=Priority.NORMAL,
        )
        return True

    # ── Admin helpers ─────────────────────────────────────────────

    def sender_stats(self) -> dict[str, Any]:
        """Доступ к статистике MessageSender для /admin_status."""
        return self._sender.stats()

    def _is_admin(self, user_id: str) -> bool:
        return user_id in self._admin_user_ids

    # ── Long-polling ─────────────────────────────────────────────

    async def poll_commands(self, stop_event: asyncio.Event) -> None:
        logger.info("=" * 50)
        logger.info("📨 TELEGRAM COMMAND POLLING STARTED")
        logger.info("   Poll interval: %s seconds", POLL_INTERVAL)
        logger.info("=" * 50)
        poll_count = 0
        while not stop_event.is_set():
            poll_count += 1
            try:
                await self._fetch_and_handle_updates()
            except Exception:
                logger.exception("Error while polling commands")
            await asyncio.sleep(POLL_INTERVAL)
        logger.info("=" * 50)
        logger.info("📨 TELEGRAM COMMAND POLLING STOPPED (total polls: %s)", poll_count)
        logger.info("=" * 50)

    async def _fetch_and_handle_updates(self) -> None:
        params: dict[str, Any] = {
            "timeout": 10,
            "allowed_updates": ["message", "callback_query"],
        }
        if self._offset is not None:
            params["offset"] = self._offset

        data = await self._client.call_api_raw("getUpdates", params)
        if data is None:
            return

        updates = data.get("result", [])
        if updates:
            logger.debug("📩 Received %s update(s) from Telegram", len(updates))

        for update in updates:
            self._offset = update.get("update_id", 0) + 1

            callback_query = update.get("callback_query")
            if callback_query is not None:
                await self._handle_callback_query(callback_query)
                continue

            message = update.get("message")
            if message is None:
                continue
            chat_id = message.get("chat", {}).get("id")
            if not chat_id:
                continue
            logger.info("💬 Message from user %s: '%s'", chat_id, (message.get("text") or "")[:80])
            await self._handle_message(str(chat_id), message)

    async def _handle_message(self, chat_id: str, message: dict[str, Any]) -> None:
        text = (message.get("text") or "").strip()
        if not text:
            logger.debug("Empty message from %s — ignoring", chat_id)
            return

        # user_id — Telegram account id отправителя (message.from.id).
        # Именно он сверяется с ADMIN_USER_IDS, а не chat_id: в приватных чатах
        # они совпадают, но семантически права привязаны к аккаунту.
        from_user = message.get("from") or {}
        user_id = str(from_user.get("id", ""))

        # ── Cancel active action ────────────────────────────────
        state = self._awaiting.get(chat_id)

        if state and text == "🔙 Назад":
            del self._awaiting[chat_id]
            logger.info("   → User %s cancelled awaiting state '%s'", chat_id, state.get("phase"))
            await self.send_message(chat_id, "❌ Действие отменено.", keyboard_kind="main")
            return

        # ── Awaiting input state ────────────────────────────────

        if state and state.get("phase") == "broadcast":
            # Админ прислал текст рассылки. Состояние могло попасть в _awaiting
            # только через __await_broadcast__, который уже проверил права, но
            # перепроверяем на случай прямого подделывания состояния.
            if not self._is_admin(user_id):
                logger.warning("⛔ Non-admin user %s in broadcast state — ignoring", chat_id)
                del self._awaiting[chat_id]
                await self.send_message(chat_id, "⛔ Нет прав для рассылки.")
                return
            del self._awaiting[chat_id]
            logger.info("   → Admin %s provided broadcast text", chat_id)
            await self._run_handler("/admin_broadcast", text, chat_id, user_id, keyboard_kind="admin")
            return

        if state and state.get("phase") == "add_type":
            # Пользователь выбрал тип поиска на reply‑кнопках
            if text == "🔗 URL":
                self._awaiting[chat_id] = {"phase": "add_name"}
                logger.info("   → User %s chose URL flow, awaiting name", chat_id)
                await self.send_message(
                    chat_id,
                    "✏️ Придумайте имя для этого поиска.\n\n"
                    "Например:\n"
                    "Кроссовки Nike",
                    keyboard_kind="cancel",
                    placeholder="Введите имя поиска...",
                )
                return
            if text == "🔤 Ключевое слово":
                self._awaiting[chat_id] = {"phase": "add_keyword"}
                logger.info("   → User %s chose keyword flow, awaiting keyword", chat_id)
                await self.send_message(
                    chat_id,
                    "🔤 Отправьте ключевое слово для поиска.\n\n"
                    "Оно же будет использовано как имя.\n\n"
                    "Например:\n"
                    "Nike кроссовки",
                    keyboard_kind="cancel",
                    placeholder="Введите ключевое слово...",
                )
                return

        if state and state.get("phase") == "add_name":
            # Пользователь прислал имя → запоминаем, просим URL
            name = text
            self._awaiting[chat_id] = {"phase": "add_url", "name": name}
            logger.info("   → User %s entered name '%s', now awaiting URL", chat_id, name)
            await self.send_message(
                chat_id,
                "🔗 Отлично! Теперь отправьте URL для этого поиска.\n\n"
                f"Имя: <b>{name}</b>\n\n"
                "Пример URL:\n"
                "https://jp.mercari.com/en/search?category_id=7021",
                keyboard_kind="cancel",
                placeholder="Введите URL...",
            )
            return

        if state and state.get("phase") == "add_url":
            # Пользователь прислал URL → вызываем /add с "url | имя"
            name = state.get("name", "")
            url = text
            del self._awaiting[chat_id]
            # Собираем как "url | имя" для существующего обработчика /add
            full_input = f"{url} | {name}" if name else url
            logger.info("   → User %s provided URL, calling /add handler", chat_id)
            await self._run_handler("/add", full_input, chat_id, user_id)
            return

        if state and state.get("phase") == "add_keyword":
            keyword = text.strip()
            del self._awaiting[chat_id]
            logger.info("   → User %s provided keyword '%s', calling /add handler", chat_id, keyword)
            await self._run_handler("/add", keyword, chat_id, user_id)
            return

        if state and state.get("phase") == "rename":
            url_id = int(state["url_id"])
            new_name = text.strip()
            del self._awaiting[chat_id]
            logger.info("   → User %s provided rename for URL #%s: '%s'", chat_id, url_id, new_name)
            if self._url_storage is None:
                await self.send_message(chat_id, "❌ Внутренняя ошибка.")
                return
            if await self._url_storage.rename(url_id, chat_id, new_name):
                logger.info("   ✅ URL #%s renamed to '%s' for user %s", url_id, new_name, chat_id)
                await self.send_message(chat_id, f"✅ URL #{url_id} переименован в: {new_name}")
            else:
                logger.warning("   ⚠️  URL #%s not found for user %s", url_id, chat_id)
                await self.send_message(chat_id, f"❌ URL #{url_id} не найден")
            return

        # ── Button press ────────────────────────────────────────
        action = BUTTON_ACTIONS.get(text)

        # Gate для админских действий: проверяем права до выполнения.
        # Не-админу кнопка не видна, но он может ввести текст кнопки вручную.
        if action in ADMIN_BUTTON_ACTIONS and not self._is_admin(user_id):
            logger.warning("⛔ Non-admin user %s pressed admin button '%s'", chat_id, text)
            await self.send_message(chat_id, "⛔ У вас нет прав администратора для этого действия.")
            return

        if action == "__await_add__":
            logger.info("   → User %s pressed 'Add' button", chat_id)
            self._awaiting[chat_id] = {"phase": "add_type"}
            await self.send_message(
                chat_id,
                "📌 Выберите тип поиска:",
                keyboard_kind="add_type",
                placeholder="Выберите URL или ключевое слово...",
            )
            return

        if action == "__await_remove__":
            logger.info("   → User %s pressed 'Remove' button", chat_id)
            await self._send_remove_inline_keyboard(chat_id)
            return

        if action == "__await_list__":
            logger.info("   → User %s pressed 'List' button", chat_id)
            await self._show_list_with_keyboard(chat_id)
            return

        if action == "__await_broadcast__":
            logger.info("   → Admin %s pressed 'Broadcast' button", chat_id)
            self._awaiting[chat_id] = {"phase": "broadcast"}
            # Ответ показываем с клавиатурой админ-панели, чтобы админ
            # оставался в контексте панели и мог нажать 🔙 Назад для отмены.
            from telegram.messages import ADMIN_BROADCAST_PROMPT
            await self.send_message(
                chat_id,
                ADMIN_BROADCAST_PROMPT,
                keyboard_kind="admin",
                placeholder="Введите текст рассылки...",
            )
            return

        if action is not None:
            logger.info("   → User %s pressed button '%s'", chat_id, text)
            # Внутри админ-панели ответы оставляют её клавиатуру;
            # /admin_back возвращает к основной.
            if action == "/admin_back":
                keyboard_kind = "main"
            elif action.startswith("/admin_"):
                keyboard_kind = "admin"
            else:
                keyboard_kind = "main"
            await self._run_handler(action, "", chat_id, user_id, keyboard_kind=keyboard_kind)
            return

        # ── Plain text as command ───────────────────────────────
        logger.info("   → User %s sent text, treating as command", chat_id)
        await self._handle_command_text(chat_id, user_id, text)

    async def _send_remove_inline_keyboard(self, chat_id: str) -> None:
        if self._url_storage is None:
            await self.send_message(chat_id, "❌ Внутренняя ошибка.")
            return
        urls = await self._url_storage.get_user_urls(chat_id)
        if not urls:
            await self.send_message(chat_id, "У вас нет отслеживаемых URL для удаления.")
            return
        markup = build_remove_inline_keyboard(urls)
        payload = {
            "chat_id": chat_id,
            "text": "🗑 <b>Выберите URL для удаления:</b>",
            "parse_mode": "HTML",
            "reply_markup": markup,
        }
        result = await self._client.call_api_json("sendMessage", payload)
        if result and result.get("ok"):
            msg = result.get("result", {})
            msg_id = msg.get("message_id")
            if msg_id:
                self._inline_msg_ids[chat_id] = msg_id
                logger.debug("   📌 Inline msg_id=%s saved for chat=%s", msg_id, chat_id)

    async def _show_list_with_keyboard(self, chat_id: str, edit_msg_id: int | None = None) -> None:
        if self._url_storage is None:
            if edit_msg_id:
                await self._client.edit_message_text(chat_id, edit_msg_id, "❌ Внутренняя ошибка.")
            else:
                await self.send_message(chat_id, "❌ Внутренняя ошибка.")
            return
        urls = await self._url_storage.get_user_urls(chat_id)
        if not urls:
            text = "У вас нет отслеживаемых URL.\nДобавьте через кнопку ➕ Добавить URL"
            markup = {"inline_keyboard": [[{"text": "🔙 Назад", "callback_data": "list_back"}]]}
        else:
            text = await format_url_list(urls, self._url_storage.count_items)
            markup = build_list_items_inline_keyboard(urls)

        if edit_msg_id:
            await self._client.edit_message_text(
                chat_id, edit_msg_id, text, reply_markup=markup,
            )
        else:
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "reply_markup": markup,
            }
            result = await self._client.call_api_json("sendMessage", payload)
            if result and result.get("ok"):
                msg = result.get("result", {})
                msg_id = msg.get("message_id")
                if msg_id:
                    self._inline_msg_ids[chat_id] = msg_id
                    logger.debug("   📌 Inline msg_id=%s saved for chat=%s", msg_id, chat_id)

    async def _handle_callback_query(self, callback_query: dict[str, Any]) -> None:
        cb_id = callback_query.get("id", "")
        data = callback_query.get("data", "")
        message = callback_query.get("message") or {}
        chat_id = str(message.get("chat", {}).get("id", ""))
        msg_id = message.get("message_id")

        if not chat_id or not data:
            logger.warning("⚠️  callback_query without chat_id or data — ignoring")
            return

        logger.info("👆 Callback from chat=%s, data='%s'", chat_id, data)

        if data == "list_back":
            await self._show_list_with_keyboard(chat_id, edit_msg_id=msg_id)
            await self._client.answer_callback_query(cb_id)
            return

        if data.startswith("info_"):
            try:
                url_id = int(data[5:])
            except ValueError:
                await self._client.answer_callback_query(cb_id, "Ошибка: некорректный ID")
                return
            if self._url_storage is None:
                await self._client.answer_callback_query(cb_id, "Внутренняя ошибка", show_alert=True)
                return
            urls = await self._url_storage.get_user_urls(chat_id)
            selected = None
            for r in urls:
                if r.id == url_id:
                    selected = r
                    break
            if selected is None:
                await self._client.answer_callback_query(cb_id, "URL не найден", show_alert=True)
                return
            detail_text = await format_url_detail(selected, self._url_storage.count_items)
            markup = build_url_detail_keyboard(url_id)
            if msg_id:
                await self._client.edit_message_text(
                    chat_id, msg_id,
                    detail_text,
                    reply_markup=markup,
                )
            await self._client.answer_callback_query(cb_id)
            return

        if data == "cancel_rename":
            if msg_id:
                await self._client.edit_message_text(
                    chat_id, msg_id, "❌ Переименование отменено.",
                )
            await self._client.answer_callback_query(cb_id)
            return

        if data == "rename_list":
            if self._url_storage is None:
                await self._client.answer_callback_query(cb_id, "Внутренняя ошибка", show_alert=True)
                return
            urls = await self._url_storage.get_user_urls(chat_id)
            if not urls:
                if msg_id:
                    await self._client.edit_message_text(
                        chat_id, msg_id, "У вас нет отслеживаемых URL.",
                    )
                await self._client.answer_callback_query(cb_id)
                return
            markup = build_rename_inline_keyboard(urls)
            if msg_id:
                await self._client.edit_message_text(
                    chat_id, msg_id,
                    "✏️ <b>Выберите URL для переименования:</b>",
                    reply_markup=markup,
                )
            await self._client.answer_callback_query(cb_id)
            return

        if data.startswith("rnm_"):
            try:
                url_id = int(data[4:])
            except ValueError:
                await self._client.answer_callback_query(cb_id, "Ошибка: некорректный ID")
                return
            urls = await self._url_storage.get_user_urls(chat_id)  # type: ignore[union-attr]
            selected = None
            for r in urls:
                if r.id == url_id:
                    selected = r
                    break
            if selected is None:
                await self._client.answer_callback_query(cb_id, "URL не найден", show_alert=True)
                return
            self._awaiting[chat_id] = {"phase": "rename", "url_id": str(url_id)}
            logger.info("   ✏️  Rename flow started for URL #%s by user %s", url_id, chat_id)
            if msg_id:
                await self._client.edit_message_text(
                    chat_id, msg_id,
                    f"✅ Выбран URL #{url_id} (<b>{selected.name}</b>).",
                )
            await self._client.answer_callback_query(cb_id)
            await self.send_message(
                chat_id,
                f"✏️ Введите новое имя для URL #{url_id} (<b>{selected.name}</b>).",
                keyboard_kind="cancel",
                placeholder="Введите новое имя...",
            )
            return

        if data == "cancel_del":
            if msg_id:
                await self._client.edit_message_text(
                    chat_id, msg_id, "❌ Удаление отменено.",
                )
            await self._client.answer_callback_query(cb_id)
            return

        if data.startswith("del_"):
            try:
                url_id = int(data[4:])
            except ValueError:
                await self._client.answer_callback_query(cb_id, "Ошибка: некорректный ID")
                return
            urls = await self._url_storage.get_user_urls(chat_id)  # type: ignore[union-attr]
            selected = None
            for r in urls:
                if r.id == url_id:
                    selected = r
                    break
            if selected is None:
                await self._client.answer_callback_query(cb_id, "URL не найден", show_alert=True)
                return
            markup = build_confirm_delete_keyboard(url_id)
            await self._client.edit_message_text(
                chat_id, msg_id,
                f"🗑 Удалить URL <b>{selected.name}</b>?",
                reply_markup=markup,
            )
            await self._client.answer_callback_query(cb_id)
            return

        if data.startswith("confirm_"):
            try:
                url_id = int(data[8:])
            except ValueError:
                await self._client.answer_callback_query(cb_id, "Ошибка: некорректный ID")
                return
            if self._url_storage is None:
                await self._client.answer_callback_query(cb_id, "Внутренняя ошибка", show_alert=True)
                return
            # Найти имя до удаления
            urls = await self._url_storage.get_user_urls(chat_id)
            name = f"#{url_id}"
            for r in urls:
                if r.id == url_id:
                    name = r.name
                    break
            deleted = await self._url_storage.remove(url_id, chat_id)
            if deleted:
                await self._client.edit_message_text(
                    chat_id, msg_id,
                    f"✅ URL <b>{name}</b> удалён.",
                )
                logger.info("   ✅ URL #%s removed via inline keyboard by %s", url_id, chat_id)
            else:
                await self._client.edit_message_text(
                    chat_id, msg_id,
                    f"❌ URL <b>{name}</b> не найден.",
                )
            await self._client.answer_callback_query(cb_id)
            return

        logger.warning("⚠️  Unknown callback_data: '%s'", data)
        await self._client.answer_callback_query(cb_id)

    async def _handle_command_text(self, chat_id: str, user_id: str, text: str) -> None:
        parts = text.split(maxsplit=1)
        command = parts[0].lower()
        argument = parts[1].strip() if len(parts) > 1 else ""
        logger.debug("   Parsed command: '%s' with argument: '%s'", command, argument[:50])
        # Intercept /list to show inline keyboard
        if command == "/list":
            await self._show_list_with_keyboard(chat_id)
            return
        # Команды /admin_* введённые напрямую — тоже с клавиатурой панели
        # (кроме /admin_back → основная). Команда /admin_broadcast без аргумента
        # вернёт приглашение ввести текст.
        if command == "/admin_back":
            keyboard_kind = "main"
        elif command.startswith("/admin_"):
            keyboard_kind = "admin"
        else:
            keyboard_kind = "main"
        placeholder: str | None = None
        if command == "/admin_broadcast" and not argument:
            placeholder = "Введите текст рассылки..."
        await self._run_handler(command, argument, chat_id, user_id, keyboard_kind=keyboard_kind, placeholder=placeholder)

    async def _run_handler(
        self,
        command: str,
        argument: str,
        chat_id: str,
        user_id: str,
        keyboard_kind: str = "main",
        placeholder: str | None = None,
    ) -> None:
        handler = self._command_handlers.get(command)
        if handler is None:
            logger.warning("   ❌ Unknown command '%s' from user %s", command, chat_id)
            await self.send_message(
                chat_id,
                f"❌ Неизвестная команда: {command}\n\n"
                "Используй кнопки внизу или /help для справки.",
            )
            return
        logger.info("   ⚡ Executing handler for '%s' (user=%s)", command, chat_id)
        try:
            response = await handler(argument, chat_id, user_id)
            logger.info("   ✅ Handler '%s' returned response (%s chars)", command, len(response))
            await self.send_message(
                chat_id, response,
                keyboard_kind=keyboard_kind,
                placeholder=placeholder,
            )
        except Exception as exc:
            logger.exception("   ❌ Command handler error for '%s'", command)
            await self.send_message(
                chat_id, f"❌ Ошибка: {exc}",
                keyboard_kind=keyboard_kind,
            )
