import logging
import time
from html import escape
from pathlib import Path
from urllib.parse import quote_plus
from datetime import datetime

from mercari.conditions import parse_search_url, normalize_search_url
from storage.urls import UrlStorage, MAX_USER_URLS
from storage.subscriptions import SubscriptionStorage
from storage.users import UserStorage
from mercari.watcher import MercariWatcher
from telegram.bot import TelegramNotifier
from telegram.messages import (
    format_admin_panel,
    format_admin_stats,
    format_broadcast_prompt,
    format_help,
    format_url_list,
    format_admin_status,
    format_promo_list,
    format_whitelist_list,
)
from telegram.i18n import text

logger = logging.getLogger(__name__)

MAX_SEARCH_URL_LENGTH = 2048
MAX_SEARCH_NAME_LENGTH = 128
MAX_KEYWORD_LENGTH = 200
MAX_BROADCAST_LENGTH = 4096

# Тип обработчика: (argument, chat_id, user_id) -> response text (async).
# user_id — Telegram account id отправителя (message.from.id); нужен для
# проверки прав администратора в админ-командах.
CommandHandler = "callable"


def _parse_add_input(text: str) -> tuple[str, str | None, str | None]:
    """Parse input: 'url', 'url | name' or 'url | name | source'.

    Returns (url, name, source). Третий сегмент распознаётся как источник
    только если он равен 'keyword' или 'url', иначе считается частью имени.
    """
    if " | " not in text:
        return text.strip(), None, None
    parts = text.split(" | ", maxsplit=2)
    url = parts[0].strip()
    if len(parts) == 3 and parts[2].strip() in {"keyword", "url"}:
        return url, parts[1].strip(), parts[2].strip()
    name = " | ".join(p.strip() for p in parts[1:]).strip()
    return url, name, None


def _parse_promo_create_input(
    raw: str,
) -> tuple[int, str, str | None, int | None, str | None, int | None] | None:
    """Parse: days | audience | target_user_id | YYYY-MM-DD expiration | custom code or - | max_uses.

    max_uses: "-" — одноразовый (1), положительное число — лимит N,
    "∞"/"0"/"unlimited" — без лимита (None).
    """
    parts = [part.strip() for part in raw.split("|")]
    if len(parts) < 2 or len(parts) > 6:
        return None

    days_part, audience = parts[0], parts[1].lower()
    if not days_part.isdigit() or int(days_part) <= 0:
        return None
    if audience not in {"all", "new_only"}:
        return None

    target: str | None = None
    if len(parts) >= 3 and parts[2] not in {"", "-", "—"}:
        if not parts[2].isdigit() or int(parts[2]) <= 0:
            return None
        target = parts[2]

    expires_at: int | None = None
    if len(parts) >= 4 and parts[3] not in {"", "-", "—"}:
        try:
            expires_at = int(
                datetime.strptime(parts[3], "%Y-%m-%d")
                .replace(hour=23, minute=59, second=59)
                .timestamp()
            )
        except ValueError:
            return None

    custom_code: str | None = None
    if len(parts) >= 5 and parts[4] not in {"", "-", "—"}:
        try:
            custom_code = SubscriptionStorage.validate_custom_promo_code(parts[4])
        except ValueError:
            return None

    max_uses: int | None = 1
    if len(parts) == 6 and parts[5] not in {"", "-", "—"}:
        token = parts[5].lower()
        if token in {"∞", "0", "unlimited", "inf"}:
            max_uses = None
        elif token.isdigit() and int(token) >= 1:
            max_uses = int(token)
        else:
            return None

    return int(days_part), audience, target, expires_at, custom_code, max_uses


def _metric(metric_stats: dict, name: str) -> float:
    """Среднее для гистограмм, сумма для счётчиков/гаугов."""
    values = metric_stats.get(name, {})
    if not values:
        return 0.0
    if "_sum" in values:
        count = values.get("_count", 0.0)
        return values["_sum"] / count if count > 0 else 0.0
    return sum(values.values())


def _metric_sum(metric_stats: dict, name: str) -> float:
    values = metric_stats.get(name, {})
    return sum(v for k, v in values.items() if not k.startswith("_"))


def _metric_error_sum(metric_stats: dict, name: str) -> float:
    """Сумма значений с лейблами-статусами, кроме успешных.

    Успех помечается как status=200 (mercari/client.py), поэтому
    ошибками считаются все остальные статусы: HTTP-коды ошибок,
    network_error, timeout, unknown.
    """
    values = metric_stats.get(name, {})
    return sum(
        v for k, v in values.items()
        if not k.startswith("_") and "status=200" not in k and "status=ok" not in k
    )


def _format_uptime(seconds: float, language: str) -> str:
    total = max(0, int(seconds))
    days, total = divmod(total, 86400)
    hours, total = divmod(total, 3600)
    minutes = total // 60
    if language == "en":
        if days:
            return f"{days}d {hours}h {minutes}m"
        if hours:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"
    if days:
        return f"{days}д {hours}ч {minutes}м"
    if hours:
        return f"{hours}ч {minutes}м"
    return f"{minutes}м"


def make_handlers(
    url_storage: UrlStorage,
    watcher: MercariWatcher,
    telegram: TelegramNotifier,
    admin_user_ids: frozenset[str] = frozenset(),
    subs_storage: SubscriptionStorage | None = None,
    metrics=None,
    started_at: float | None = None,
    db_path: Path | None = None,
    user_storage: UserStorage | None = None,
) -> dict:
    """Create a dict of async command handlers for TelegramNotifier.

    Каждый обработчик имеет сигнатуру (arg, chat_id, user_id) -> str.
    """

    def _is_admin(user_id: str) -> bool:
        return user_id in admin_user_ids

    async def _check_subscription(chat_id: str, user_id: str, language: str) -> str | None:
        """Returns None if access allowed, or an error message if not."""
        if subs_storage is None:
            return None
        if _is_admin(user_id):
            return None
        if await subs_storage.is_whitelisted(chat_id):
            return None
        if not await subs_storage.is_subscribed(chat_id):
            return text("no_subscription", language)
        return None

    # ── Пользовательские команды ──────────────────────────────────

    async def cmd_help(_arg: str, chat_id: str, _user_id: str, language: str) -> str:
        logger.info("💬 /help requested by user %s", chat_id)
        return format_help(language)

    async def cmd_add(url: str, chat_id: str, _user_id: str, language: str) -> str:
        logger.info("💬 /add from user %s: '%s'", chat_id, url[:100])

        err = await _check_subscription(chat_id, _user_id, language)
        if err:
            return err

        if not url:
            logger.warning("   ⚠️  Empty input from user %s", chat_id)
            return text("provide_search", language)

        clean_url, name, source = _parse_add_input(url)
        if not clean_url:
            return text("provide_search", language)
        if len(clean_url) > MAX_SEARCH_URL_LENGTH or (name is not None and len(name) > MAX_SEARCH_NAME_LENGTH):
            return text("url_input_too_long", language)

        # If input is not a URL, treat it as a keyword → construct Mercari search URL
        if not clean_url.startswith("http"):
            keyword = clean_url
            clean_url = (
                "https://jp.mercari.com/en/search?"
                f"keyword={quote_plus(keyword)}&sort=created_time&order=desc"
            )
            if not name:
                name = keyword
            if source is None:
                source = "keyword"
            logger.info("   🔤 Keyword '%s' converted to search URL", keyword)

        if source is None:
            source = "url"

        if not clean_url.startswith("https://jp.mercari.com"):
            logger.warning("   ⚠️  Invalid domain from user %s: %s", chat_id, clean_url[:50])
            return text("invalid_domain", language)

        if source == "keyword" and len(name or "") > MAX_KEYWORD_LENGTH:
            return text("url_input_too_long", language)

        # Validate URL by parsing it into a SearchCondition
        try:
            parse_search_url(clean_url)
        except Exception as exc:
            logger.error("   ❌ URL parse failed for user %s: %s", chat_id, exc)
            return text("url_parse_error", language, error=escape(str(exc)))

        clean_url = normalize_search_url(clean_url)
        logger.debug("   🔧 Normalized URL: %s", clean_url)

        try:
            is_new, url_id = await url_storage.add(clean_url, chat_id, name, source)
        except ValueError as exc:
            if "Maximum" in str(exc):
                return text("url_limit_reached", language, limit=MAX_USER_URLS)
            raise
        if is_new:
            watcher.force_reload()
            display_name = name or clean_url
            logger.info("   ✅ URL #%s added for user %s (name='%s')", url_id, chat_id, display_name)
            return text("url_added", language, name=escape(display_name))
        logger.info("   ℹ️  URL already exists for user %s (id=%s)", chat_id, url_id)
        return text("url_exists", language)

    async def cmd_remove(arg: str, chat_id: str, _user_id: str, language: str) -> str:
        logger.info("💬 /remove from user %s: '%s'", chat_id, arg)

        err = await _check_subscription(chat_id, _user_id, language)
        if err:
            return err

        if not arg or not arg.isdigit():
            logger.warning("   ⚠️  Invalid ID from user %s: '%s'", chat_id, arg)
            return text("invalid_id", language)
        url_id = int(arg)
        if await url_storage.remove(url_id, chat_id):
            logger.info("   ✅ URL #%s removed for user %s", url_id, chat_id)
            return text("url_deleted", language)
        logger.warning("   ⚠️  URL #%s not found for user %s", url_id, chat_id)
        return text("url_not_found", language)

    async def cmd_rename(arg: str, chat_id: str, _user_id: str, language: str) -> str:
        logger.info("💬 /rename from user %s: '%s'", chat_id, arg[:80])

        err = await _check_subscription(chat_id, _user_id, language)
        if err:
            return err

        """/rename id | new name"""
        if not arg or " | " not in arg:
            return text("rename_usage", language)
        id_part, new_name = arg.split(" | ", maxsplit=1)
        if not id_part.isdigit() or not new_name.strip():
            return text("rename_usage", language)

        url_id = int(id_part)
        name = new_name.strip()

        target = next(
            (r for r in await url_storage.get_user_urls(chat_id) if r.id == url_id),
            None,
        )
        if target is None:
            logger.warning("   ⚠️  URL #%s not found for user %s", url_id, chat_id)
            return text("url_not_found", language)
        if target.source == "keyword":
            logger.warning("   ⚠️  Refusing to rename keyword-based URL #%s for user %s", url_id, chat_id)
            return text("rename_not_allowed", language)

        if await url_storage.rename(url_id, chat_id, name):
            logger.info("   ✅ URL #%s renamed to '%s' for user %s", url_id, name, chat_id)
            return text("url_renamed", language, name=escape(name))
        logger.warning("   ⚠️  URL #%s not found for user %s", url_id, chat_id)
        return text("url_not_found", language)

    async def cmd_list(_arg: str, chat_id: str, _user_id: str, language: str) -> str:
        logger.info("💬 /list from user %s", chat_id)
        urls = await url_storage.get_user_urls(chat_id)
        logger.info("   📋 User %s has %s URL(s)", chat_id, len(urls))
        return await format_url_list(urls, language=language)

    async def cmd_reload(_arg: str, chat_id: str, user_id: str, language: str) -> str:
        if not _is_admin(user_id):
            logger.warning("⛔ Non-admin user %s tried /reload", chat_id)
            return text("no_permission", language)
        logger.info("🔄 Admin reload requested by user %s — forcing immediate check", chat_id)
        watcher.force_reload()
        return text("reload_started", language)

    # ── Команды администратора ────────────────────────────────────
    #
    # Каждая команда перепроверяет права через _is_admin(user_id) — это
    # защита в глубину: gate в bot.py уже отсекает не-админов по кнопкам,
    # но здесь отсекается прямой ввод /admin_* в чате.

    async def cmd_admin_panel(_arg: str, chat_id: str, user_id: str, language: str) -> str:
        if not _is_admin(user_id):
            logger.warning("⛔ Non-admin user %s tried /admin_panel", chat_id)
            return text("no_permission", language)
        logger.info("🛠 Admin panel opened by user %s", chat_id)
        return format_admin_panel(language)

    async def cmd_admin_status(_arg: str, chat_id: str, user_id: str, language: str) -> str:
        if not _is_admin(user_id):
            logger.warning("⛔ Non-admin user %s tried /admin_status", chat_id)
            return text("no_permission", language)
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
            language=language,
        )

    async def cmd_admin_stats(_arg: str, chat_id: str, user_id: str, language: str) -> str:
        if not _is_admin(user_id):
            logger.warning("⛔ Non-admin user %s tried /admin_stats", chat_id)
            return text("no_permission", language)
        logger.info("📈 Admin stats requested by user %s", chat_id)

        metric_stats: dict = metrics.get_stats() if metrics is not None else {}
        sender_stats = telegram.sender_stats()

        cycles = int(_metric_sum(metric_stats, "mercabot_watch_cycle_total"))
        cycle_errors = int(_metric_sum(metric_stats, "mercabot_watch_cycle_errors_total"))
        avg_cycle = _metric(metric_stats, "mercabot_watch_cycle_duration_seconds")
        requests = int(_metric_sum(metric_stats, "mercabot_mercari_requests_total"))
        request_errors = int(_metric_error_sum(metric_stats, "mercabot_mercari_requests_total"))
        avg_latency = _metric(metric_stats, "mercabot_mercari_request_duration_seconds")
        items_found = int(_metric_sum(metric_stats, "mercabot_items_found_total"))
        sent = int(_metric_sum(metric_stats, "mercabot_notifications_sent_total"))
        failed = int(_metric_sum(metric_stats, "mercabot_notifications_failed_total"))
        rate_limited = int(_metric_sum(metric_stats, "mercabot_telegram_429_total"))

        url_stats = await url_storage.get_stats()
        subs_stats = await subs_storage.get_stats() if subs_storage is not None else {}
        users_count = (
            await user_storage.count()
            if user_storage is not None
            else len(await url_storage.get_all_user_chat_ids())
        )

        by_status = subs_stats.get("by_status", {})
        by_plan = subs_stats.get("by_plan", {})
        plans_str = ", ".join(
            f"{plan}: {by_plan[plan]}" for plan in sorted(by_plan)
        ) or "—"
        revenue = subs_stats.get("revenue", {})
        revenue_str = ", ".join(
            f"{asset}: {amount:,.2f}" for asset, amount in sorted(revenue.items())
        ) or "—"

        uptime = (
            _format_uptime(time.time() - started_at, language)
            if started_at is not None else "—"
        )
        db_size_mb = "—"
        if db_path is not None:
            try:
                db_size_mb = f"{db_path.stat().st_size / (1024 * 1024):.1f}"
            except OSError:
                db_size_mb = "—"

        return format_admin_stats(
            language=language,
            uptime=uptime,
            cycles=cycles,
            cycle_errors=cycle_errors,
            avg_cycle=f"{avg_cycle:.1f}",
            requests=requests,
            request_errors=request_errors,
            avg_latency=f"{avg_latency:.2f}",
            items_found=items_found,
            sent=sent,
            failed=failed,
            rate_limited=rate_limited,
            queue=sender_stats.get("queue_size", 0),
            outbox=url_stats.get("outbox", 0),
            users=users_count,
            urls_active=url_stats.get("urls_active", 0),
            urls_total=url_stats.get("urls_total", 0),
            subs_active=by_status.get("active", 0),
            subs_pending=by_status.get("pending", 0),
            subs_expired=by_status.get("expired", 0) + by_status.get("cancelled", 0),
            plans=plans_str,
            promo_users=subs_stats.get("promo_users", 0),
            whitelist=subs_stats.get("whitelist", 0),
            revenue=revenue_str,
            db_size=db_size_mb,
            items_total=url_stats.get("items_total", 0),
            items_today=url_stats.get("items_today", 0),
            seen_total=url_stats.get("seen_total", 0),
        )

    async def cmd_admin_pause(_arg: str, chat_id: str, user_id: str, language: str) -> str:
        if not _is_admin(user_id):
            logger.warning("⛔ Non-admin user %s tried /admin_pause", chat_id)
            return text("no_permission", language)
        logger.info("⏸️ Admin pause requested by user %s", chat_id)
        watcher.pause()
        return text("admin_pause", language)

    async def cmd_admin_resume(_arg: str, chat_id: str, user_id: str, language: str) -> str:
        if not _is_admin(user_id):
            logger.warning("⛔ Non-admin user %s tried /admin_resume", chat_id)
            return text("no_permission", language)
        logger.info("▶️ Admin resume requested by user %s", chat_id)
        watcher.resume()
        return text("admin_resume", language)

    async def cmd_admin_reload(_arg: str, chat_id: str, user_id: str, language: str) -> str:
        if not _is_admin(user_id):
            logger.warning("⛔ Non-admin user %s tried /admin_reload", chat_id)
            return text("no_permission", language)
        logger.info("🔄 Admin reload requested by user %s — forcing immediate check", chat_id)
        watcher.force_reload()
        return text("reload_started", language)

    async def cmd_admin_back(_arg: str, chat_id: str, user_id: str, language: str) -> str:
        if not _is_admin(user_id):
            logger.warning("⛔ Non-admin user %s tried /admin_back", chat_id)
            return text("no_permission", language)
        logger.info("🔙 Admin left admin panel (user %s)", chat_id)
        return text("admin_back", language)

    async def cmd_admin_broadcast(message_text: str, chat_id: str, user_id: str, language: str) -> str:
        if not _is_admin(user_id):
            logger.warning("⛔ Non-admin user %s tried /admin_broadcast", chat_id)
            return text("no_permission", language)
        if not message_text:
            return format_broadcast_prompt(language)
        if len(message_text) > MAX_BROADCAST_LENGTH:
            return text("broadcast_too_long", language)
        logger.info("📢 Admin broadcast from user %s: '%s'", chat_id, message_text[:80])

        chat_ids: set[str] = set()
        if user_storage is not None:
            chat_ids |= await user_storage.get_all_chat_ids()
        chat_ids |= await url_storage.get_all_user_chat_ids()
        sent = 0
        for cid in chat_ids:
            # Рассылка идёт через очередь MessageSender с дросселированием,
            # как и обычные сообщения. Клавиатуру не показываем (kind="none"),
            # чтобы не менять текущее состояние клавиатуры получателей.
            await telegram.send_message(
                cid,
                text(
                    "broadcast_header",
                    await telegram.get_language(cid),
                    text=message_text,
                ),
                show_keyboard=True,
            )
            sent += 1
        logger.info("   ✅ Broadcast delivered to %s users", sent)
        return text("broadcast_sent", language, count=sent)

    async def cmd_admin_whitelist(_arg: str, chat_id: str, user_id: str, language: str) -> str:
        if not _is_admin(user_id):
            logger.warning("⛔ Non-admin user %s tried /admin_whitelist", chat_id)
            return text("no_permission", language)
        logger.info("👥 Admin whitelist panel opened by user %s", chat_id)
        return text("whitelist_prompt", language)

    async def cmd_admin_whitelist_grant(target_user_id: str, chat_id: str, user_id: str, language: str) -> str:
        if not _is_admin(user_id):
            logger.warning("⛔ Non-admin user %s tried /admin_whitelist_grant", chat_id)
            return text("no_permission", language)
        if not target_user_id or not target_user_id.strip():
            return text("whitelist_grant_prompt", language)
        target = target_user_id.strip()
        try:
            int(target)
        except ValueError:
            return text("whitelist_grant_prompt", language)
        if subs_storage is None:
            return text("internal_error", language)
        added = await subs_storage.whitelist_add(target, user_id)
        if added:
            logger.info("👤 Admin %s granted access to user %s", user_id, target)
            return text("whitelist_granted", language, user_id=target)
        return text("whitelist_already_granted", language, user_id=target)

    async def cmd_admin_whitelist_revoke(target_user_id: str, chat_id: str, user_id: str, language: str) -> str:
        if not _is_admin(user_id):
            logger.warning("⛔ Non-admin user %s tried /admin_whitelist_revoke", chat_id)
            return text("no_permission", language)
        if not target_user_id or not target_user_id.strip():
            return text("whitelist_revoke_prompt", language)
        target = target_user_id.strip()
        try:
            int(target)
        except ValueError:
            return text("whitelist_revoke_prompt", language)
        if subs_storage is None:
            return text("internal_error", language)
        removed = await subs_storage.whitelist_remove(target)
        if removed:
            logger.info("👤 Admin %s revoked access from user %s", user_id, target)
            return text("whitelist_revoked", language, user_id=target)
        return text("whitelist_not_found", language, user_id=target)

    async def cmd_admin_whitelist_list(_arg: str, chat_id: str, user_id: str, language: str) -> str:
        if not _is_admin(user_id):
            logger.warning("⛔ Non-admin user %s tried /admin_whitelist_list", chat_id)
            return text("no_permission", language)
        if subs_storage is None:
            return text("internal_error", language)
        entries = await subs_storage.whitelist_list()
        logger.info("📋 Admin %s requested whitelist (%s entries)", chat_id, len(entries))
        return format_whitelist_list(entries, language)

    async def cmd_admin_promos(_arg: str, chat_id: str, user_id: str, language: str) -> str:
        if not _is_admin(user_id):
            logger.warning("⛔ Non-admin user %s tried /admin_promos", chat_id)
            return text("no_permission", language)
        logger.info("🎟 Admin promo panel opened by user %s", chat_id)
        return text("promo_panel", language)

    async def cmd_admin_promo_create(argument: str, chat_id: str, user_id: str, language: str) -> str:
        if not _is_admin(user_id):
            logger.warning("⛔ Non-admin user %s tried /admin_promo_create", chat_id)
            return text("no_permission", language)
        if not argument.strip():
            return text("promo_create_prompt", language)
        if subs_storage is None:
            return text("internal_error", language)

        parsed = _parse_promo_create_input(argument)
        if parsed is None:
            return text("promo_create_invalid", language)
        days, audience, target, expires_at, custom_code, max_uses = parsed
        try:
            promo = await subs_storage.create_promo(
                duration_days=days,
                audience=audience,
                created_by=user_id,
                target_user_id=target,
                expires_at=expires_at,
                custom_code=custom_code,
                max_uses=max_uses,
            )
        except ValueError as exc:
            logger.warning("⚠️ Invalid promo creation request from admin %s", user_id)
            if custom_code is not None and "already exists" in str(exc):
                return text("promo_create_taken", language, code=escape(custom_code))
            return text("promo_create_invalid", language)

        audience_label = text(
            "promo_audience_new_only" if audience == "new_only" else "promo_audience_all",
            language,
        )
        target_label = target or text("promo_never", language)
        uses_label = (
            text("promo_uses_unlimited", language)
            if max_uses is None else str(max_uses)
        )
        expires_label = (
            datetime.fromtimestamp(expires_at).strftime("%d.%m.%Y")
            if expires_at is not None else text("promo_never", language)
        )
        return text(
            "promo_created",
            language,
            code=escape(promo.code),
            days=days,
            audience=audience_label,
            target=escape(target_label),
            uses=uses_label,
            expires=expires_label,
        )

    async def cmd_admin_promo_list(_arg: str, chat_id: str, user_id: str, language: str) -> str:
        if not _is_admin(user_id):
            logger.warning("⛔ Non-admin user %s tried /admin_promo_list", chat_id)
            return text("no_permission", language)
        if subs_storage is None:
            return text("internal_error", language)
        entries = await subs_storage.list_promos()
        logger.info("📋 Admin %s requested promo list (%s entries)", chat_id, len(entries))
        return format_promo_list(entries, language)

    async def cmd_admin_promo_deactivate(code: str, chat_id: str, user_id: str, language: str) -> str:
        if not _is_admin(user_id):
            logger.warning("⛔ Non-admin user %s tried /admin_promo_deactivate", chat_id)
            return text("no_permission", language)
        if not code.strip():
            return text("promo_deactivate_prompt", language)
        if subs_storage is None:
            return text("internal_error", language)
        normalized = subs_storage.normalize_promo_code(code)
        if await subs_storage.deactivate_promo(normalized):
            return text("promo_deactivated", language, code=escape(normalized))
        return text("promo_deactivate_not_found", language, code=escape(normalized))

    async def cmd_admin_promo_delete(code: str, chat_id: str, user_id: str, language: str) -> str:
        if not _is_admin(user_id):
            logger.warning("⛔ Non-admin user %s tried /admin_promo_delete", chat_id)
            return text("no_permission", language)
        if not code.strip():
            return text("promo_delete_prompt", language)
        if subs_storage is None:
            return text("internal_error", language)
        normalized = subs_storage.normalize_promo_code(code)
        if await subs_storage.delete_promo(normalized):
            return text("promo_deleted", language, code=escape(normalized))
        return text("promo_delete_not_found", language, code=escape(normalized))

    return {
        # ── пользовательские ──
        "/help": cmd_help,
        "/add": cmd_add,
        "/remove": cmd_remove,
        "/rename": cmd_rename,
        "/list": cmd_list,
        "/reload": cmd_reload,
        # ── администраторские ──
        "/admin_panel": cmd_admin_panel,
        "/admin_status": cmd_admin_status,
        "/admin_stats": cmd_admin_stats,
        "/admin_reload": cmd_admin_reload,
        "/admin_pause": cmd_admin_pause,
        "/admin_resume": cmd_admin_resume,
        "/admin_back": cmd_admin_back,
        "/admin_broadcast": cmd_admin_broadcast,
        "/admin_whitelist": cmd_admin_whitelist,
        "/admin_whitelist_grant": cmd_admin_whitelist_grant,
        "/admin_whitelist_revoke": cmd_admin_whitelist_revoke,
        "/admin_whitelist_list": cmd_admin_whitelist_list,
        "/admin_promos": cmd_admin_promos,
        "/admin_promo_create": cmd_admin_promo_create,
        "/admin_promo_list": cmd_admin_promo_list,
        "/admin_promo_deactivate": cmd_admin_promo_deactivate,
        "/admin_promo_delete": cmd_admin_promo_delete,
    }
