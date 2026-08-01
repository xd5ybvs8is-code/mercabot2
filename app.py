import asyncio
import logging
import signal
import sys
from pathlib import Path

from config import load_settings
from mercari.client import MercariClient
from mercari.devices import DeviceRegistry
from mercari.watcher import MercariWatcher
from storage.connection import DatabaseConnection
from storage.urls import UrlStorage
from storage.users import UserStorage
from telegram.bot import TelegramNotifier
from telegram.handlers import make_handlers
from telegram.messages import format_shutdown, format_startup

BASE_DIR = Path(__file__).resolve().parent


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s] %(asctime)s %(message)s",
        datefmt="%H:%M:%S",
    )


def _install_signal_handlers(loop: asyncio.AbstractEventLoop, watcher: MercariWatcher) -> None:
    def request_shutdown() -> None:
        logger = logging.getLogger(__name__)
        logger.info("=" * 50)
        logger.info("⚠️  SHUTDOWN REQUESTED — signal received (SIGINT/SIGTERM)")
        logger.info("=" * 50)
        watcher.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, request_shutdown)
        except NotImplementedError:
            signal.signal(sig, lambda _signum, _frame: request_shutdown())


async def _notify_all_users(
    telegram: TelegramNotifier,
    url_storage: UrlStorage,
    message_key: str,
) -> None:
    """Sends a message to all users who have URLs in the database."""
    logger = logging.getLogger(__name__)
    chat_ids = await url_storage.get_all_user_chat_ids()
    logger.info("Sending notification to %s users: %s", len(chat_ids), message_key)
    for chat_id in chat_ids:
        language = await telegram.get_language(chat_id)
        message = format_startup(language) if message_key == "startup" else format_shutdown(language)
        await telegram.send_message(chat_id, message)
    logger.info("Notification sent to all %s users", len(chat_ids))


async def main() -> None:
    setup_logging()
    logger = logging.getLogger(__name__)

    logger.info("=" * 50)
    logger.info("🚀 MERCABOT STARTING UP")
    logger.info("=" * 50)

    # ── 1. Load settings ─────────────────────────────────────────
    logger.info("─" * 40)
    logger.info("STEP 1/7: Loading configuration...")
    try:
        settings = load_settings()
    except ValueError as exc:
        logger.error("❌ Configuration error: %s", exc)
        sys.exit(1)
    logger.info("✅ Configuration loaded successfully")
    logger.info("   DB path: %s", settings.db_path)
    logger.info("   Check interval: %s seconds", settings.check_interval)
    logger.info("   Max concurrency: %s", settings.max_concurrency)
    logger.info("   Request delay: %s seconds", settings.request_delay)
    logger.info("   Telegram token: %s...%s", settings.telegram_token[:5], settings.telegram_token[-5:])
    logger.info("   TG send rate: %s msg/sec (chat interval: %ss)", settings.tg_send_rate, settings.tg_chat_min_interval)
    logger.info("   Admin users: %s (%s)", len(settings.admin_user_ids), sorted(settings.admin_user_ids) or "none")

    # ── 2. Database ──────────────────────────────────────────────
    logger.info("─" * 40)
    logger.info("STEP 2/7: Connecting to database...")
    db = DatabaseConnection(settings.db_path)
    await db.connect()
    logger.info("✅ Database connected and schema verified")

    # ── 3. URL Storage ──────────────────────────────────────────
    logger.info("─" * 40)
    logger.info("STEP 3/7: Initializing URL storage...")
    url_storage = UrlStorage(db)
    user_storage = UserStorage(db)
    active_urls = await url_storage.get_active_urls()
    logger.info("✅ URL storage initialized")
    logger.info("   Active search URLs: %s", len(active_urls))
    for i, url_row in enumerate(active_urls, 1):
        logger.info("   [%s] #%s — %s (user: %s)", i, url_row.id, url_row.name, url_row.user_chat_id)

    # ── 4. Device Registry (per-user DPoP-личности) ─────────────
    logger.info("─" * 40)
    logger.info("STEP 4/7: Initializing device registry...")
    devices = DeviceRegistry(db)
    logger.info("✅ Device registry ready (per-user device_uuid via DB + in-memory cache)")

    # ── 5. Mercari Client ───────────────────────────────────────
    logger.info("─" * 40)
    logger.info("STEP 5/7: Starting Mercari API client...")
    # dpop=None: дефолтной «общей» личности больше нет — каждый запрос
    # подписывается per-user signer'ом, переданным в client.search(...).
    client = MercariClient(
        max_concurrency=settings.max_concurrency,
        request_delay=settings.request_delay,
    )
    await client.start()
    logger.info("✅ Mercari client started")
    logger.info("   Max concurrency: %s", settings.max_concurrency)
    logger.info("   Request delay: %s", settings.request_delay)
    logger.info("   API URL: https://api.mercari.jp/v2/entities:search")

    # ── 6. Telegram Bot ─────────────────────────────────────────
    logger.info("─" * 40)
    logger.info("STEP 6/7: Starting Telegram bot...")
    telegram = TelegramNotifier(
        settings.telegram_token,
        rate_per_sec=settings.tg_send_rate,
        chat_min_interval=settings.tg_chat_min_interval,
        admin_user_ids=settings.admin_user_ids,
        url_storage=url_storage,
        user_storage=user_storage,
    )
    watcher = MercariWatcher(settings, url_storage, telegram, client, devices)

    handlers = make_handlers(url_storage, watcher, telegram, settings.admin_user_ids)
    telegram.register_commands(handlers)
    logger.info("   Registered %s command handlers", len(handlers))
    for cmd in handlers:
        logger.info("   → %s", cmd)

    loop = asyncio.get_running_loop()
    _install_signal_handlers(loop, watcher)

    await telegram.start()
    logger.info("✅ Telegram bot started")

    # ── 7. Polling Loop ──────────────────────────────────────────
    logger.info("─" * 40)
    logger.info("STEP 7/7: Starting command polling...")
    stop_event = asyncio.Event()
    poll_task = asyncio.create_task(telegram.poll_commands(stop_event))
    logger.info("✅ Command polling loop started (interval: 2s)")

    # ── Start notification ──────────────────────────────────────
    logger.info("=" * 50)
    logger.info("🎯 BOT IS RUNNING")
    logger.info("=" * 50)

    await _notify_all_users(telegram, url_storage, "startup")
    logger.info("Bot started. Users can interact via Telegram.")

    cleanup_task = asyncio.create_task(watcher.cleanup_loop())

    try:
        await watcher.run()
    finally:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
        logger.info("=" * 50)
        logger.info("🛑 SHUTTING DOWN...")
        logger.info("=" * 50)

        logger.info("  • Notifying users about shutdown...")
        await _notify_all_users(telegram, url_storage, "shutdown")

        logger.info("  • Stopping command polling...")
        stop_event.set()
        await poll_task
        logger.info("  ✅ Polling stopped")

        logger.info("  • Closing Mercari client...")
        await client.aclose()
        logger.info("  ✅ Mercari client closed")

        logger.info("  • Closing Telegram bot...")
        await telegram.close()
        logger.info("  ✅ Telegram bot closed")

        logger.info("  • Closing database...")
        await db.close()
        logger.info("  ✅ Database closed")

        logger.info("=" * 50)
        logger.info("✅ SHUTDOWN COMPLETE")
        logger.info("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
