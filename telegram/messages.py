from html import escape
from datetime import datetime

from models.item import Item
from storage.urls import SearchUrlRow
from telegram.i18n import text

def format_help(language: str) -> str:
    return text("help", language)


def format_startup(language: str) -> str:
    return text("startup", language)


def format_shutdown(language: str) -> str:
    return text("shutdown", language)


def format_item_notification(item: Item, search_name: str, language: str = "ru") -> str:
    return (
        f"{escape(search_name)}\n\n"
        + text(
            "new_listing",
            language,
            title=escape(item.title),
            price=item.price,
            url=escape(item.url),
        )
    )


async def format_url_list(
    urls: list[SearchUrlRow],
    page: int | None = None, total_pages: int | None = None,
    language: str = "ru",
) -> str:
    if not urls:
        return text("no_urls", language)
    if page is not None and total_pages is not None:
        return text("url_list", language, page=page + 1, total=total_pages)
    return text("url_list_short", language)


async def format_url_detail(row: SearchUrlRow, language: str = "ru") -> str:
    added_by = text(
        "keyword_source" if row.source == "keyword" else "url_source", language,
    )
    return text(
        "url_detail", language,
        name=escape(row.name), url=escape(row.url), source=added_by,
    )


# ── Admin panel ─────────────────────────────────────────────────

def format_admin_panel(language: str) -> str:
    return text("admin_panel", language)


def format_broadcast_prompt(language: str) -> str:
    return text("broadcast_prompt", language)


def format_not_authorized(language: str) -> str:
    return text("no_permission", language)


def format_admin_status(
    *,
    paused: bool,
    queue_size: int,
    current_rate: int,
    target_rate: int,
    active_urls: int,
    users: int,
    language: str = "ru",
) -> str:
    state = text("paused" if paused else "running", language)
    return text(
        "admin_status", language,
        state=state, queue=queue_size, current=current_rate,
        target=target_rate, urls=active_urls, users=users,
    )


def format_admin_stats(*, language: str = "ru", **values: object) -> str:
    return text("admin_stats", language, **values)


def format_whitelist_list(entries: list[tuple[str, str, int]], language: str = "ru") -> str:
    result = text("whitelist_list_title", language)
    if not entries:
        result += text("whitelist_list_empty", language)
    else:
        for user_id, granted_by, granted_at in entries:
            dt = datetime.fromtimestamp(granted_at).strftime("%d.%m.%Y %H:%M")
            result += text("whitelist_list_row", language, user_id=user_id, granted_by=granted_by, granted_at=dt)
    return result

