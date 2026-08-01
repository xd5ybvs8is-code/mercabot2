from urllib.parse import parse_qs, urlparse

from models.item import Item
from storage.urls import SearchUrlRow

HELP_TEXT = (
    "Mercari Watcher Bot\n\n"
    "Commands:\n\n"
    "/add <keyword or url> | <name> -- add search to track\n"
    "/remove <id> -- delete search by ID\n"
    "/rename <id> | <new name> -- rename search\n"
    "/list -- show all tracked searches\n"
    "/help -- this message\n\n"
    "Keyword example:\n"
    "/add Nike Sneakers | My Search\n\n"
    "URL example:\n"
    "/add https://jp.mercari.com/en/search?category_id=7021 | Nike Sneakers"
)

STARTUP_MESSAGE = (
    "Mercari Watcher started\n\n"
    "Bot started tracking new listings."
)

SHUTDOWN_MESSAGE = (
    "Mercari Watcher stopped\n\n"
    "Bot has shut down."
)


def format_item_notification(item: Item, search_name: str) -> str:
    return (
        f"{search_name}\n\n"
        "New listing\n\n"
        f"Title:\n{item.title}\n\n"
        f"Price:\n{item.price:,} JPY\n\n"
        f"Link:\n{item.url}"
    )


async def format_url_list(
    urls: list[SearchUrlRow],
    page: int | None = None, total_pages: int | None = None,
) -> str:
    if not urls:
        return "No tracked URLs.\nAdd one via the Add URL button"
    if page is not None and total_pages is not None:
        return f"Ваши URL (страница {page + 1}/{total_pages}):"
    return "Ваши URL:"


async def format_url_detail(row: SearchUrlRow) -> str:
    parsed = urlparse(row.url)
    params = parse_qs(parsed.query)
    added_by = "ключевому слову" if "keyword" in params else "прямой ссылке"

    return (
        f"<b>{row.name}</b>\n\n"
        f"🔗 <b>URL парсинга:</b>\n{row.url}\n\n"
        f"📌 <b>Добавлен по:</b> {added_by}"
    )


# ── Admin panel ─────────────────────────────────────────────────

ADMIN_PANEL_TEXT = (
    "🛠 <b>Админ-панель</b>\n\n"
    "Доступные действия:\n"
    "📊 <b>Статус бота</b> — сводка состояния\n"
    "🔄 <b>Перезагрузить URL</b> — немедленный цикл проверки\n"
    "⏸️ <b>Пауза</b> / ▶️ <b>Продолжить</b> — остановка/возобновление watcher'а\n"
    "📢 <b>Рассылка всем</b> — отправить сообщение всем пользователям\n"
    "🔙 <b>Назад</b> — выйти из админ-панели"
)

ADMIN_BROADCAST_PROMPT = (
    "📢 <b>Рассылка всем</b>\n\n"
    "Отправьте текст сообщения, которое получат все пользователи бота.\n"
    "Поддерживается HTML-разметка Telegram.\n\n"
    "Для отмены отправьте /admin_back."
)

NOT_AUTHORIZED = "⛔ У вас нет прав администратора для этого действия."


def format_admin_status(
    *,
    paused: bool,
    queue_size: int,
    current_rate: int,
    target_rate: int,
    active_urls: int,
    users: int,
) -> str:
    state = "⏸️ ПРИОСТАНОВЛЕН" if paused else "▶️ работает"
    return (
        "📊 <b>Статус бота</b>\n\n"
        f"Watcher: {state}\n"
        f"Очередь сообщений: {queue_size}\n"
        f"Скорость отправки: {current_rate}/{target_rate} msg/s\n"
        f"Активных URL: {active_urls}\n"
        f"Пользователей: {users}"
    )

