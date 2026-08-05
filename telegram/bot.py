import asyncio
from html import escape
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from typing import TYPE_CHECKING

from telegram.client import TelegramClient
from telegram.keyboard import (
    BUTTON_ACTIONS,
    ADMIN_BUTTON_ACTIONS,
    PAGE_SIZE,
    build_confirm_delete_keyboard,
    build_list_items_inline_keyboard_paginated,
    build_url_detail_keyboard,
    build_rename_inline_keyboard,
    build_language_keyboard,
    build_help_inline_keyboard,
    build_terms_inline_keyboard,
    build_subscription_inline_keyboard,
    LANGUAGE_BUTTON,
    button_text,
)
from telegram.i18n import text as tr
from telegram.messages import format_item_notification, format_url_detail, format_url_list
from telegram.sender import MessageSender, Priority
from models.item import Item
from storage.urls import PendingNotification
from storage.users import UserStorage

if TYPE_CHECKING:
    from storage.urls import UrlStorage

logger = logging.getLogger(__name__)

POLL_INTERVAL = 2.0

# Handler type: (argument, chat_id, user_id) -> response text (async).
# user_id — Telegram account id отправителя (message.from.id), нужен для
# проверки прав администратора в админ-командах.
CommandHandler = Callable[[str, str, str, str], Awaitable[str]]


class TelegramNotifier:
    """High-level bot: message sending, command polling, button routing."""

    def __init__(
        self,
        token: str,
        rate_per_sec: int = 20,
        chat_min_interval: float = 1.0,
        admin_user_ids: frozenset[str] = frozenset(),
        url_storage: "UrlStorage | None" = None,
        user_storage: UserStorage | None = None,
    ) -> None:
        self._client = TelegramClient(token)
        self._admin_user_ids = admin_user_ids
        self._url_storage = url_storage
        self._user_storage = user_storage
        self._sender = MessageSender(
            self._client,
            rate_per_sec=rate_per_sec,
            chat_min_interval=chat_min_interval,
            admin_user_ids=admin_user_ids,
            on_chat_lost=self._on_chat_lost,
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
        # Текущая страница пагинации для списка (по chat_id)
        self._list_pages: dict[str, int] = {}

    async def start(self) -> None:
        logger.info("⏳ Starting Telegram bot...")
        await self._client.start()
        if self._url_storage is not None:
            pending = await self._url_storage.get_pending_notifications()
            for notification in pending:
                self._enqueue_pending_notification(notification)
            logger.info("📦 Restored %s pending notification(s) from outbox", len(pending))
        self._sender.start()
        logger.info("✅ Telegram bot started (long-polling mode)")

    async def close(self) -> None:
        logger.info("⏳ Closing Telegram bot...")
        # Сначала дренажируем очередь отправки, потом гасим клиент.
        await self._sender.stop()
        await self._client.close()
        logger.info("✅ Telegram bot closed")

    async def _on_chat_lost(self, chat_id: str) -> None:
        """Clean up a chat that Telegram reports as permanently gone."""
        logger.info("🧹 Chat %s lost — deactivating URLs", chat_id)
        if self._url_storage is not None:
            await self._url_storage.deactivate_chat(chat_id)

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
        language = await self._get_language(chat_id)
        self._sender.enqueue(
            chat_id,
            text,
            disable_preview=disable_preview,
            show_keyboard=show_keyboard,
            priority=Priority.HIGH,
            keyboard_kind=keyboard_kind,
            language=language,
            placeholder=placeholder,
        )
        return True

    async def send_item(
        self,
        chat_id: str,
        item: Item,
        search_name: str = "",
        *,
        search_url_id: int | None = None,
    ) -> bool:
        language = await self._get_language(chat_id)
        notification_text = format_item_notification(item, search_name, language)
        if self._url_storage is None:
            self._sender.enqueue(
                chat_id, notification_text, disable_preview=False, show_keyboard=False,
                priority=Priority.NORMAL,
                language=language,
            )
            return True

        if search_url_id is None:
            raise ValueError("search_url_id is required for durable item notifications")
        notification = await self._url_storage.add_pending_notification(
            search_url_id=search_url_id,
            item_id=item.id,
            chat_id=chat_id,
            text=notification_text,
        )
        if notification is not None:
            self._enqueue_pending_notification(notification)
        return True

    def _enqueue_pending_notification(self, notification: PendingNotification) -> None:
        async def acknowledge() -> None:
            if self._url_storage is None:
                return
            await self._url_storage.complete_notification(
                notification.id, notification.search_url_id, notification.item_id,
            )

        self._sender.enqueue(
            notification.chat_id,
            notification.text,
            disable_preview=False,
            show_keyboard=False,
            priority=Priority.NORMAL,
            language="ru",
            on_success=acknowledge,
        )

    async def _get_language(self, chat_id: str) -> str:
        if self._user_storage is None:
            return "ru"
        return (await self._user_storage.get_language(chat_id)) or "ru"

    async def get_language(self, chat_id: str) -> str:
        """Return the selected language for a chat."""
        return await self._get_language(chat_id)

    async def _show_language_selection(self, chat_id: str, edit_msg_id: int | None = None) -> None:
        payload = {
            "chat_id": chat_id,
            "text": tr("language_prompt", "ru"),
            "reply_markup": build_language_keyboard(),
        }
        if edit_msg_id is not None:
            await self._client.edit_message_text(
                chat_id, edit_msg_id, payload["text"],
                reply_markup=payload["reply_markup"],
            )
        else:
            await self._client.call_api_json("sendMessage", payload)

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
        language = await self._get_language(chat_id)

        # The language button is available even while another flow is active.
        if text == LANGUAGE_BUTTON:
            self._awaiting.pop(chat_id, None)
            await self._show_language_selection(chat_id)
            return

        stored_language = (
            await self._user_storage.get_language(chat_id)
            if self._user_storage is not None else "ru"
        )
        if stored_language is None:
            await self._show_language_selection(chat_id)
            return

        if text.split(maxsplit=1)[0].lower() == "/start":
            if self._url_storage is not None:
                reactivated = await self._url_storage.reactivate_chat(chat_id)
                if reactivated > 0:
                    logger.info(
                        "🔄 /start from returning user %s: reactivated %s URL(s)",
                        chat_id, reactivated,
                    )
            await self.send_message(chat_id, tr("welcome", language))
            return

        # ── Cancel active action ────────────────────────────────
        state = self._awaiting.get(chat_id)

        if state and text in {button_text("back", language), "🔙 Назад", "🔙 Back"}:
            del self._awaiting[chat_id]
            logger.info("   → User %s cancelled awaiting state '%s'", chat_id, state.get("phase"))
            await self.send_message(chat_id, tr("cancelled", language), keyboard_kind="main")
            return

        # ── Awaiting input state ────────────────────────────────

        if state and state.get("phase") == "broadcast":
            # Админ прислал текст рассылки. Состояние могло попасть в _awaiting
            # только через __await_broadcast__, который уже проверил права, но
            # перепроверяем на случай прямого подделывания состояния.
            if not self._is_admin(user_id):
                logger.warning("⛔ Non-admin user %s in broadcast state — ignoring", chat_id)
                del self._awaiting[chat_id]
                await self.send_message(chat_id, tr("no_permission", language))
                return
            del self._awaiting[chat_id]
            logger.info("   → Admin %s provided broadcast text", chat_id)
            await self._run_handler("/admin_broadcast", text, chat_id, user_id, keyboard_kind="admin")
            return

        if state and state.get("phase") == "add_type":
            # Пользователь выбрал тип поиска на reply‑кнопках
            if text in {button_text("url_type", language), "🔗 URL"}:
                self._awaiting[chat_id] = {"phase": "add_name"}
                logger.info("   → User %s chose URL flow, awaiting name", chat_id)
                await self.send_message(
                    chat_id,
                    tr("enter_search_name", language),
                    keyboard_kind="cancel",
                    placeholder=tr("name_placeholder", language),
                )
                return
            if text in {button_text("keyword_type", language), "🔤 Ключевое слово"}:
                self._awaiting[chat_id] = {"phase": "add_keyword"}
                logger.info("   → User %s chose keyword flow, awaiting keyword", chat_id)
                await self.send_message(
                    chat_id,
                    tr("enter_keyword", language),
                    keyboard_kind="cancel",
                    placeholder=tr("keyword_placeholder", language),
                )
                return

        if state and state.get("phase") == "add_name":
            # Пользователь прислал имя → запоминаем, просим URL
            name = text
            self._awaiting[chat_id] = {"phase": "add_url", "name": name}
            logger.info("   → User %s entered name '%s', now awaiting URL", chat_id, name)
            await self.send_message(
                chat_id,
                tr("enter_url", language, name=escape(name)),
                keyboard_kind="cancel",
                placeholder=tr("url_placeholder", language),
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
                await self.send_message(chat_id, tr("internal_error", language))
                return
            if await self._url_storage.rename(url_id, chat_id, new_name):
                logger.info("   ✅ URL #%s renamed to '%s' for user %s", url_id, new_name, chat_id)
                await self.send_message(chat_id, tr("url_renamed", language, name=escape(new_name)))
            else:
                logger.warning("   ⚠️  URL #%s not found for user %s", url_id, chat_id)
                await self.send_message(chat_id, tr("url_not_found", language))
            return

        # ── Button press ────────────────────────────────────────
        action = BUTTON_ACTIONS.get(text)

        # Gate для админских действий: проверяем права до выполнения.
        # Не-админу кнопка не видна, но он может ввести текст кнопки вручную.
        if action in ADMIN_BUTTON_ACTIONS and not self._is_admin(user_id):
            logger.warning("⛔ Non-admin user %s pressed admin button '%s'", chat_id, text)
            await self.send_message(chat_id, tr("no_permission", language))
            return

        if action == "__await_add__":
            logger.info("   → User %s pressed 'Add' button", chat_id)
            self._awaiting[chat_id] = {"phase": "add_type"}
            await self.send_message(
                chat_id,
                tr("choose_search_type", language),
                keyboard_kind="add_type",
                placeholder=tr("type_placeholder", language),
            )
            return

        if action == "__language__":
            await self._show_language_selection(chat_id)
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
            await self.send_message(
                chat_id,
                tr("broadcast_prompt", language),
                keyboard_kind="admin",
                placeholder=tr("broadcast_placeholder", language),
            )
            return

        if action == "__await_subscription__":
            logger.info("   → User %s pressed 'Subscription' button", chat_id)
            await self._show_subscription(chat_id)
            return

        if action is not None:
            logger.info("   → User %s pressed button '%s'", chat_id, text)

            if action == "/help":
                await self._show_help_inline(chat_id)
                return

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

    async def _show_list_with_keyboard(self, chat_id: str, edit_msg_id: int | None = None) -> None:
        language = await self._get_language(chat_id)
        if self._url_storage is None:
            if edit_msg_id:
                await self._client.edit_message_text(chat_id, edit_msg_id, tr("internal_error", language))
            else:
                await self.send_message(chat_id, tr("internal_error", language))
            return
        urls = await self._url_storage.get_user_urls(chat_id)
        if not urls:
            self._list_pages.pop(chat_id, None)
            list_text = tr("no_urls", language)
            markup = {"inline_keyboard": [[{
                "text": "🔙 Back" if language == "en" else "🔙 Назад",
                "callback_data": "list_back",
            }]]}
        else:
            page = self._list_pages.get(chat_id, 0)
            total_pages = (len(urls) + PAGE_SIZE - 1) // PAGE_SIZE
            if page >= total_pages:
                page = total_pages - 1
            self._list_pages[chat_id] = page

            start = page * PAGE_SIZE
            page_urls = urls[start:start + PAGE_SIZE]

            list_text = await format_url_list(
                page_urls,
                page=page, total_pages=total_pages,
                language=language,
            )
            markup = build_list_items_inline_keyboard_paginated(
                page_urls, page, total_pages, language=language,
            )

        if edit_msg_id:
            ok = await self._client.edit_message_text(
                chat_id, edit_msg_id, list_text, reply_markup=markup,
            )
            if not ok:
                logger.warning("⚠️  Failed to edit message for chat=%s, sending new message", chat_id)
                payload = {
                    "chat_id": chat_id,
                    "text": list_text,
                    "parse_mode": "HTML",
                    "reply_markup": markup,
                }
                await self._client.call_api_json("sendMessage", payload)
        else:
            payload = {
                "chat_id": chat_id,
                "text": list_text,
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

    async def _show_help_inline(self, chat_id: str, edit_msg_id: int | None = None) -> None:
        language = await self._get_language(chat_id)
        help_text = tr("help", language)
        markup = build_help_inline_keyboard(language)
        if edit_msg_id:
            await self._client.edit_message_text(
                chat_id, edit_msg_id, help_text, reply_markup=markup,
            )
        else:
            payload = {
                "chat_id": chat_id,
                "text": help_text,
                "parse_mode": "HTML",
                "reply_markup": markup,
            }
            result = await self._client.call_api_json("sendMessage", payload)
            if result and result.get("ok"):
                msg = result.get("result", {})
                msg_id = msg.get("message_id")
                if msg_id:
                    self._inline_msg_ids[chat_id] = msg_id
                    logger.debug("   📌 Help inline msg_id=%s saved for chat=%s", msg_id, chat_id)

    async def _show_terms_inline(self, chat_id: str, msg_id: int | None) -> None:
        language = await self._get_language(chat_id)
        terms_text = tr("terms_of_use_text", language)
        markup = build_terms_inline_keyboard(language)
        if msg_id:
            await self._client.edit_message_text(
                chat_id, msg_id, terms_text, reply_markup=markup,
            )

    async def _show_subscription(self, chat_id: str) -> None:
        language = await self._get_language(chat_id)
        sub_text = tr("subscription_title", language)
        markup = build_subscription_inline_keyboard(language)
        payload = {
            "chat_id": chat_id,
            "text": sub_text,
            "parse_mode": "HTML",
            "reply_markup": markup,
        }
        result = await self._client.call_api_json("sendMessage", payload)
        if result and result.get("ok"):
            msg = result.get("result", {})
            msg_id = msg.get("message_id")
            if msg_id:
                self._inline_msg_ids[chat_id] = msg_id
                logger.debug("   📌 Subscription inline msg_id=%s saved for chat=%s", msg_id, chat_id)

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

        try:
            await self._dispatch_callback(cb_id, data, chat_id, msg_id)
        except Exception:
            logger.exception("❌ Unhandled error in callback handler (data='%s')", data)
            try:
                await self._client.answer_callback_query(
                    cb_id,
                    "An error occurred" if await self._get_language(chat_id) == "en" else "Произошла ошибка",
                    show_alert=True,
                )
            except Exception:
                logger.exception("❌ Failed to answer callback query after error")


    async def _dispatch_callback(self, cb_id: str, data: str, chat_id: str, msg_id: int | None) -> None:
        language = await self._get_language(chat_id)

        if data == "terms_open":
            await self._show_terms_inline(chat_id, msg_id)
            await self._client.answer_callback_query(cb_id)
            return

        if data == "terms_back":
            await self._show_help_inline(chat_id, edit_msg_id=msg_id)
            await self._client.answer_callback_query(cb_id)
            return

        if data in ("sub_7d", "sub_30d"):
            await self._client.answer_callback_query(cb_id)
            return

        if data == "change_language":
            await self._show_language_selection(chat_id, edit_msg_id=msg_id)
            await self._client.answer_callback_query(cb_id)
            return

        if data in {"lang_ru", "lang_en"}:
            language = data.removeprefix("lang_")
            previous_language = (
                await self._user_storage.get_language(chat_id)
                if self._user_storage is not None else None
            )
            if self._user_storage is not None:
                await self._user_storage.set_language(chat_id, language)
            if msg_id:
                await self._client.edit_message_text(
                    chat_id, msg_id, tr("language_saved", language),
                    reply_markup={"inline_keyboard": []},
                )
            await self._client.answer_callback_query(cb_id)
            await self.send_message(
                chat_id,
                tr("welcome" if previous_language is None else "language_changed", language),
                keyboard_kind="main",
            )
            return

        if data == "list_back":
            self._list_pages[chat_id] = 0
            await self._show_list_with_keyboard(chat_id, edit_msg_id=msg_id)
            await self._client.answer_callback_query(cb_id)
            return

        if data == "list_prev":
            self._list_pages[chat_id] = max(0, self._list_pages.get(chat_id, 0) - 1)
            await self._show_list_with_keyboard(chat_id, edit_msg_id=msg_id)
            await self._client.answer_callback_query(cb_id)
            return

        if data == "list_next":
            self._list_pages[chat_id] = self._list_pages.get(chat_id, 0) + 1
            await self._show_list_with_keyboard(chat_id, edit_msg_id=msg_id)
            await self._client.answer_callback_query(cb_id)
            return

        if data == "none":
            await self._client.answer_callback_query(cb_id)
            return

        if data.startswith("info_"):
            try:
                url_id = int(data[5:])
            except ValueError:
                await self._client.answer_callback_query(cb_id, "Invalid ID" if language == "en" else "Некорректный ID")
                return
            if self._url_storage is None:
                await self._client.answer_callback_query(cb_id, tr("internal_error", language), show_alert=True)
                return
            urls = await self._url_storage.get_user_urls(chat_id)
            selected = None
            for r in urls:
                if r.id == url_id:
                    selected = r
                    break
            if selected is None:
                await self._client.answer_callback_query(cb_id, tr("url_not_found", language), show_alert=True)
                return
            detail_text = await format_url_detail(selected, language)
            markup = build_url_detail_keyboard(url_id, language)
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
                    chat_id, msg_id, tr("rename_cancelled", language),
                )
            await self._client.answer_callback_query(cb_id)
            return

        if data == "rename_list":
            if self._url_storage is None:
                await self._client.answer_callback_query(cb_id, tr("internal_error", language), show_alert=True)
                return
            urls = await self._url_storage.get_user_urls(chat_id)
            if not urls:
                if msg_id:
                    await self._client.edit_message_text(
                        chat_id, msg_id, tr("no_urls", language),
                    )
                await self._client.answer_callback_query(cb_id)
                return
            markup = build_rename_inline_keyboard(urls, language)
            if msg_id:
                await self._client.edit_message_text(
                    chat_id, msg_id,
                    tr("rename_choose", language),
                    reply_markup=markup,
                )
            await self._client.answer_callback_query(cb_id)
            return

        if data.startswith("rnm_"):
            try:
                url_id = int(data[4:])
            except ValueError:
                await self._client.answer_callback_query(cb_id, "Invalid ID" if language == "en" else "Некорректный ID")
                return
            urls = await self._url_storage.get_user_urls(chat_id)  # type: ignore[union-attr]
            selected = None
            for r in urls:
                if r.id == url_id:
                    selected = r
                    break
            if selected is None:
                await self._client.answer_callback_query(cb_id, tr("url_not_found", language), show_alert=True)
                return
            self._awaiting[chat_id] = {"phase": "rename", "url_id": str(url_id)}
            logger.info("   ✏️  Rename flow started for URL #%s by user %s", url_id, chat_id)
            if msg_id:
                await self._client.edit_message_text(
                    chat_id, msg_id,
                    tr("rename_selected", language, name=escape(selected.name)),
                )
            await self._client.answer_callback_query(cb_id)
            await self.send_message(
                chat_id,
                tr("rename_prompt", language, name=escape(selected.name)),
                keyboard_kind="cancel",
                placeholder="Enter a new name..." if language == "en" else "Введите новое имя...",
            )
            return

        if data == "cancel_del":
            self._list_pages[chat_id] = 0
            await self._show_list_with_keyboard(chat_id, edit_msg_id=msg_id)
            await self._client.answer_callback_query(cb_id)
            return

        if data.startswith("del_"):
            try:
                url_id = int(data[4:])
            except ValueError:
                await self._client.answer_callback_query(cb_id, "Invalid ID" if language == "en" else "Некорректный ID")
                return
            urls = await self._url_storage.get_user_urls(chat_id)  # type: ignore[union-attr]
            selected = None
            for r in urls:
                if r.id == url_id:
                    selected = r
                    break
            if selected is None:
                await self._client.answer_callback_query(cb_id, tr("url_not_found", language), show_alert=True)
                return
            markup = build_confirm_delete_keyboard(url_id, language)
            ok = await self._client.edit_message_text(
                chat_id, msg_id,
                tr("delete_confirm", language, name=escape(selected.name)),
                reply_markup=markup,
            )
            if not ok:
                await self._client.answer_callback_query(
                    cb_id,
                    "Error updating the message" if language == "en" else "Ошибка при обновлении сообщения",
                    show_alert=True,
                )
                return
            await self._client.answer_callback_query(cb_id)
            return

        if data.startswith("confirm_"):
            try:
                url_id = int(data[8:])
            except ValueError:
                await self._client.answer_callback_query(cb_id, "Invalid ID" if language == "en" else "Некорректный ID")
                return
            if self._url_storage is None:
                await self._client.answer_callback_query(cb_id, tr("internal_error", language), show_alert=True)
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
                self._list_pages[chat_id] = 0
                await self._client.edit_message_text(
                    chat_id, msg_id,
                    tr("deleted", language, name=escape(name)),
                    reply_markup={"inline_keyboard": []},
                )
                logger.info("   ✅ URL #%s removed via inline keyboard by %s", url_id, chat_id)
            else:
                await self._client.edit_message_text(
                    chat_id, msg_id,
                    tr("not_found_named", language, name=escape(name)),
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
        # Intercept /help to show inline keyboard
        if command == "/help":
            await self._show_help_inline(chat_id)
            return
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
            placeholder = tr("broadcast_placeholder", await self._get_language(chat_id))
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
        language = await self._get_language(chat_id)
        if handler is None:
            logger.warning("   ❌ Unknown command '%s' from user %s", command, chat_id)
            await self.send_message(
                chat_id,
                tr("unknown_command", language, command=escape(command)),
            )
            return
        logger.info("   ⚡ Executing handler for '%s' (user=%s)", command, chat_id)
        try:
            response = await handler(argument, chat_id, user_id, language)
            logger.info("   ✅ Handler '%s' returned response (%s chars)", command, len(response))
            await self.send_message(
                chat_id, response,
                keyboard_kind=keyboard_kind,
                placeholder=placeholder,
            )
        except Exception as exc:
            logger.exception("   ❌ Command handler error for '%s'", command)
            await self.send_message(
                chat_id, tr("error", language, error=escape(str(exc))),
                keyboard_kind=keyboard_kind,
            )
