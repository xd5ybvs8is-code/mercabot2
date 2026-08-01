import logging
from urllib.parse import quote_plus

from mercari.conditions import parse_search_url, normalize_search_url
from storage.urls import UrlStorage
from mercari.watcher import MercariWatcher
from telegram.bot import TelegramNotifier
from telegram.messages import (
    ADMIN_PANEL_TEXT,
    ADMIN_BROADCAST_PROMPT,
    HELP_TEXT,
    NOT_AUTHORIZED,
    format_admin_status,
    format_url_list,
    format_stats,
)

logger = logging.getLogger(__name__)

# Тип обработчика: (argument, chat_id, user_id) -> response text (async).
# user_id — Telegram account id отправителя (message.from.id); нужен для
# проверки прав администратора в админ-командах.
CommandHandler = "callable"


def _parse_add_input(text: str) -> tuple[str, str | None]:
    """Parse input: 'url | name' or just 'url'. Returns (url, name)."""
    if " | " in text:
        parts = text.split(" | ", maxsplit=1)
        return parts[0].strip(), parts[1].strip()
    return text.strip(), None


def make_handlers(
    url_storage: UrlStorage,
    watcher: MercariWatcher,
    telegram: TelegramNotifier,
    admin_user_ids: frozenset[str] = frozenset(),
) -> dict:
    """Create a dict of async command handlers for TelegramNotifier.

    Каждый обработчик имеет сигнатуру (arg, chat_id, user_id) -> str.
    """

    def _is_admin(user_id: str) -> bool:
        return user_id in admin_user_ids

    # ── Пользовательские команды ──────────────────────────────────

    async def cmd_help(_arg: str, chat_id: str, _user_id: str) -> str:
        logger.info("💬 /help requested by user %s", chat_id)
        return HELP_TEXT

    async def cmd_add(url: str, chat_id: str, _user_id: str) -> str:
        logger.info("💬 /add from user %s: '%s'", chat_id, url[:100])
        if not url:
            logger.warning("   ⚠️  Empty input from user %s", chat_id)
            return (
                "Provide a keyword or URL.\n\n"
                "Keyword example:\n"
                "/add Nike Sneakers | My Search\n\n"
                "URL example:\n"
                "/add https://jp.mercari.com/en/search?category_id=7021 | Nike Sneakers"
            )

        clean_url, name = _parse_add_input(url)
        if not clean_url:
            return (
                "Provide a keyword or URL.\n\n"
                "Keyword example:\n"
                "/add Nike Sneakers | My Search\n\n"
                "URL example:\n"
                "/add https://jp.mercari.com/en/search?category_id=7021 | Nike Sneakers"
            )

        # If input is not a URL, treat it as a keyword → construct Mercari search URL
        if not clean_url.startswith("http"):
            keyword = clean_url
            clean_url = (
                "https://jp.mercari.com/en/search?"
                f"keyword={quote_plus(keyword)}&sort=created_time&order=desc"
            )
            if not name:
                name = keyword
            logger.info("   🔤 Keyword '%s' converted to search URL", keyword)

        if not clean_url.startswith("https://jp.mercari.com"):
            logger.warning("   ⚠️  Invalid domain from user %s: %s", chat_id, clean_url[:50])
            return "URL must be from jp.mercari.com"

        # Validate URL by parsing it into a SearchCondition
        try:
            parse_search_url(clean_url)
        except Exception as exc:
            logger.error("   ❌ URL parse failed for user %s: %s", chat_id, exc)
            return f"Could not parse search URL: {exc}"

        clean_url = normalize_search_url(clean_url)
        logger.debug("   🔧 Normalized URL: %s", clean_url)

        is_new, url_id = await url_storage.add(clean_url, chat_id, name)
        if is_new:
            watcher.force_reload()
            display_name = name or clean_url
            logger.info("   ✅ URL #%s added for user %s (name='%s')", url_id, chat_id, display_name)
            return f"URL added\nName: {display_name}\n\nFirst check will start on next cycle"
        logger.info("   ℹ️  URL already exists for user %s (id=%s)", chat_id, url_id)
        return "URL already exists"

    async def cmd_remove(arg: str, chat_id: str, _user_id: str) -> str:
        logger.info("💬 /remove from user %s: '%s'", chat_id, arg)
        if not arg or not arg.isdigit():
            logger.warning("   ⚠️  Invalid ID from user %s: '%s'", chat_id, arg)
            return "Provide URL ID to delete. Example:\n/remove 2"
        url_id = int(arg)
        if await url_storage.remove(url_id, chat_id):
            logger.info("   ✅ URL #%s removed for user %s", url_id, chat_id)
            return "URL deleted"
        logger.warning("   ⚠️  URL #%s not found for user %s", url_id, chat_id)
        return "URL not found"

    async def cmd_rename(arg: str, chat_id: str, _user_id: str) -> str:
        logger.info("💬 /rename from user %s: '%s'", chat_id, arg[:80])
        """/rename id | new name"""
        if not arg or " | " not in arg:
            return "Provide ID and new name. Example:\n/rename 2 | Adidas Sneakers"
        id_part, new_name = arg.split(" | ", maxsplit=1)
        if not id_part.isdigit() or not new_name.strip():
            return "Provide ID and new name. Example:\n/rename 2 | Adidas Sneakers"

        url_id = int(id_part)
        name = new_name.strip()
        if await url_storage.rename(url_id, chat_id, name):
            logger.info("   ✅ URL #%s renamed to '%s' for user %s", url_id, name, chat_id)
            return f"URL renamed to: {name}"
        logger.warning("   ⚠️  URL #%s not found for user %s", url_id, chat_id)
        return "URL not found"

    async def cmd_list(_arg: str, chat_id: str, _user_id: str) -> str:
        logger.info("💬 /list from user %s", chat_id)
        urls = await url_storage.get_user_urls(chat_id)
        logger.info("   📋 User %s has %s URL(s)", chat_id, len(urls))
        return await format_url_list(urls, url_storage.count_items)

    async def cmd_stats(_arg: str, chat_id: str, _user_id: str) -> str:
        logger.info("💬 /stats from user %s", chat_id)
        urls = await url_storage.get_user_urls(chat_id)
        logger.info("   📊 Generating stats for user %s (%s URLs)", chat_id, len(urls))
        return await format_stats(urls, url_storage.count_items)

    async def cmd_reload(_arg: str, chat_id: str, user_id: str) -> str:
        if not _is_admin(user_id):
            logger.warning("⛔ Non-admin user %s tried /reload", chat_id)
            return NOT_AUTHORIZED
        logger.info("🔄 Admin reload requested by user %s — forcing immediate check", chat_id)
        watcher.force_reload()
        return "🔄 Немедленная перезагрузка всех URL инициирована."

    # ── Команды администратора ────────────────────────────────────
    #
    # Каждая команда перепроверяет права через _is_admin(user_id) — это
    # защита в глубину: gate в bot.py уже отсекает не-админов по кнопкам,
    # но здесь отсекается прямой ввод /admin_* в чате.

    async def cmd_admin_panel(_arg: str, chat_id: str, user_id: str) -> str:
        if not _is_admin(user_id):
            logger.warning("⛔ Non-admin user %s tried /admin_panel", chat_id)
            return NOT_AUTHORIZED
        logger.info("🛠 Admin panel opened by user %s", chat_id)
        return ADMIN_PANEL_TEXT

    async def cmd_admin_status(_arg: str, chat_id: str, user_id: str) -> str:
        if not _is_admin(user_id):
            logger.warning("⛔ Non-admin user %s tried /admin_status", chat_id)
            return NOT_AUTHORIZED
        logger.info("📊 Admin status requested by user %s", chat_id)

        sender_stats = telegram.sender_stats()
        active_urls = await url_storage.get_active_urls()
        users = await url_storage.get_all_user_chat_ids()
        return format_admin_status(
            paused=watcher.paused,
            queue_size=sender_stats.get("queue_size", 0),
            current_rate=sender_stats.get("current_rate", 0),
            target_rate=sender_stats.get("target_rate", 0),
            active_urls=len(active_urls),
            users=len(users),
        )

    async def cmd_admin_pause(_arg: str, chat_id: str, user_id: str) -> str:
        if not _is_admin(user_id):
            logger.warning("⛔ Non-admin user %s tried /admin_pause", chat_id)
            return NOT_AUTHORIZED
        logger.info("⏸️ Admin pause requested by user %s", chat_id)
        watcher.pause()
        return "⏸️ Watcher приостановлен. Циклы проверки пропускаются до команды ▶️ Продолжить."

    async def cmd_admin_resume(_arg: str, chat_id: str, user_id: str) -> str:
        if not _is_admin(user_id):
            logger.warning("⛔ Non-admin user %s tried /admin_resume", chat_id)
            return NOT_AUTHORIZED
        logger.info("▶️ Admin resume requested by user %s", chat_id)
        watcher.resume()
        return "▶️ Watcher возобновлён. Циклы проверки продолжатся."

    async def cmd_admin_reload(_arg: str, chat_id: str, user_id: str) -> str:
        if not _is_admin(user_id):
            logger.warning("⛔ Non-admin user %s tried /admin_reload", chat_id)
            return NOT_AUTHORIZED
        logger.info("🔄 Admin reload requested by user %s — forcing immediate check", chat_id)
        watcher.force_reload()
        return "🔄 Немедленная перезагрузка всех URL инициирована."

    async def cmd_admin_back(_arg: str, chat_id: str, user_id: str) -> str:
        if not _is_admin(user_id):
            logger.warning("⛔ Non-admin user %s tried /admin_back", chat_id)
            return NOT_AUTHORIZED
        logger.info("🔙 Admin left admin panel (user %s)", chat_id)
        return "Вы вышли из админ-панели."

    async def cmd_admin_broadcast(text: str, chat_id: str, user_id: str) -> str:
        if not _is_admin(user_id):
            logger.warning("⛔ Non-admin user %s tried /admin_broadcast", chat_id)
            return NOT_AUTHORIZED
        if not text:
            return ADMIN_BROADCAST_PROMPT
        logger.info("📢 Admin broadcast from user %s: '%s'", chat_id, text[:80])

        chat_ids = await url_storage.get_all_user_chat_ids()
        sent = 0
        for cid in chat_ids:
            # Рассылка идёт через очередь MessageSender с дросселированием,
            # как и обычные сообщения. Клавиатуру не показываем (kind="none"),
            # чтобы не менять текущее состояние клавиатуры получателей.
            await telegram.send_message(
                cid,
                f"📢 <b>Сообщение от администратора</b>\n\n{text}",
                show_keyboard=True,
            )
            sent += 1
        logger.info("   ✅ Broadcast delivered to %s users", sent)
        return f"📢 Сообщение отправлено {sent} пользователю(ям)."

    return {
        # ── пользовательские ──
        "/help": cmd_help,
        "/add": cmd_add,
        "/remove": cmd_remove,
        "/rename": cmd_rename,
        "/list": cmd_list,
        "/stats": cmd_stats,
        "/reload": cmd_reload,
        # ── администраторские ──
        "/admin_panel": cmd_admin_panel,
        "/admin_status": cmd_admin_status,
        "/admin_reload": cmd_admin_reload,
        "/admin_pause": cmd_admin_pause,
        "/admin_resume": cmd_admin_resume,
        "/admin_back": cmd_admin_back,
        "/admin_broadcast": cmd_admin_broadcast,
    }
