from html import escape
from datetime import datetime

from models.item import Item
from storage.urls import SearchUrlRow
from storage.subscriptions import PromoCodeRow
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


def format_promo_list(entries: list[PromoCodeRow], language: str = "ru") -> str:
    result = text("promo_list_title", language)
    if not entries:
        return result + text("promo_list_empty", language)

    now = int(datetime.now().timestamp())
    for promo in entries:
        if promo.max_uses is not None and promo.redemption_count >= promo.max_uses:
            status_key = "promo_status_used"
        elif not promo.active:
            status_key = "promo_status_inactive"
        elif promo.expires_at is not None and promo.expires_at <= now:
            status_key = "promo_status_expired"
        else:
            status_key = "promo_status_active"

        audience_key = "promo_audience_new_only" if promo.audience == "new_only" else "promo_audience_all"
        expires = (
            datetime.fromtimestamp(promo.expires_at).strftime("%d.%m.%Y")
            if promo.expires_at is not None else text("promo_never", language)
        )
        if promo.redemption_count == 0:
            redeemed = text("promo_never", language)
        else:
            max_label = "∞" if promo.max_uses is None else str(promo.max_uses)
            redeemed = f"{promo.redemption_count}/{max_label}"
            if promo.redeemed_by is not None:
                redeemed += f" — {escape(promo.redeemed_by)}"
                if promo.redeemed_at is not None:
                    redeemed += f" ({datetime.fromtimestamp(promo.redeemed_at).strftime('%d.%m.%Y %H:%M')})"

        result += text(
            "promo_list_row",
            language,
            code=escape(promo.code),
            days=promo.duration_days,
            audience=text(audience_key, language),
            status=text(status_key, language),
            target=escape(promo.target_user_id) if promo.target_user_id else text("promo_never", language),
            expires=expires,
            redeemed=redeemed,
        )
    return result

