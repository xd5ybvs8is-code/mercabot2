import asyncio
import json
import logging
import signal
import sys
import time
from pathlib import Path

from config import load_settings
from crypto.client import CryptoPayClient
from platega.client import PlategaClient
from mercari.client import MercariClient
from mercari.devices import DeviceRegistry
from mercari.watcher import MercariWatcher
from storage.connection import DatabaseConnection
from storage.subscriptions import SubscriptionStorage
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


async def _poll_invoices_loop(
    crypto_client: CryptoPayClient,
    subs_storage: SubscriptionStorage,
    telegram: TelegramNotifier,
    interval: float = 30.0,
) -> None:
    """Periodically check pending invoices and activate paid subscriptions."""
    logger = logging.getLogger(__name__)
    logger.info("=" * 50)
    logger.info("🔄 INVOICE POLLING LOOP STARTED")
    logger.info("   Interval: %s seconds", interval)
    logger.info("=" * 50)
    while True:
        try:
            expired_pending = await subs_storage.get_expired_pending(timeout_minutes=30)
            if expired_pending:
                logger.info("⏰ %s expired pending invoice(s) found — cancelling", len(expired_pending))
            for sub in expired_pending:
                if sub.payment_gateway == "platega":
                    continue
                await subs_storage.cancel_pending(sub.user_id)
                language = await telegram.get_language(sub.user_id)
                await telegram.send_message(
                    sub.user_id,
                    "⏰ Счёт на оплату отменён.\n\nВремя на оплату истекло (30 минут). Создайте новый счёт."
                    if language == "ru"
                    else "⏰ Invoice cancelled.\n\nPayment time expired (30 minutes). Create a new invoice.",
                )

            pending = await subs_storage.get_pending_invoices()
            if pending:
                invoice_ids = [s.invoice_id for s in pending if s.invoice_id is not None and s.payment_gateway != "platega"]
                if invoice_ids:
                    invoices = await crypto_client.get_invoices(invoice_ids)
                    paid_map = {i.invoice_id: i for i in invoices if i.status == "paid"}
                    if paid_map:
                        logger.info("💰 %s paid invoice(s) found for pending subscriptions", len(paid_map))
                    for sub in pending:
                        if sub.payment_gateway == "platega":
                            continue
                        if sub.invoice_id in paid_map:
                            inv = paid_map[sub.invoice_id]
                            plan_days = subs_storage.get_plan_days(sub.plan)
                            expires_at = int(time.time()) + plan_days * 86400
                            await subs_storage.activate(
                                user_id=sub.user_id,
                                plan=sub.plan,
                                invoice_id=sub.invoice_id,
                                payment_hash=inv.hash,
                                paid_amount=inv.amount,
                                paid_asset=inv.asset,
                                expires_at=expires_at,
                            )
                            language = await telegram.get_language(sub.user_id)
                            from datetime import datetime
                            expires_str = datetime.fromtimestamp(expires_at).strftime("%d.%m.%Y %H:%M")
                            await telegram.send_message(
                                sub.user_id,
                                f"✅ Подписка активирована!\n\n📦 {sub.plan} дней\n⏰ До: {expires_str}",
                            )
        except Exception:
            logger.exception("Invoice polling error")
        await asyncio.sleep(interval)


async def _expire_subscriptions_loop(
    subs_storage: SubscriptionStorage,
    url_storage: UrlStorage,
    interval: float = 600.0,
) -> None:
    """Periodically mark expired subscriptions and deactivate their URLs."""
    logger = logging.getLogger(__name__)
    logger.info("=" * 50)
    logger.info("⏰ SUBSCRIPTION EXPIRY CHECKER STARTED")
    logger.info("   Interval: %s seconds", interval)
    logger.info("=" * 50)
    while True:
        try:
            expired = await subs_storage.get_all_expired_active()
            if expired:
                logger.info("⏰ %s expired subscription(s) found", len(expired))
            for sub in expired:
                await subs_storage.mark_expired(sub.user_id)
                await url_storage.deactivate_chat(sub.user_id)
                logger.info("⏰ Expired subscription for user %s — URLs deactivated", sub.user_id)
        except Exception:
            logger.exception("Expiry checker error")
        await asyncio.sleep(interval)


async def _poll_platega_loop(
    platega_client: PlategaClient,
    subs_storage: SubscriptionStorage,
    telegram: TelegramNotifier,
    interval: float = 30.0,
) -> None:
    """Periodically check pending Platega payments and activate paid subscriptions."""
    logger = logging.getLogger(__name__)
    logger.info("=" * 50)
    logger.info("🔄 PLATEGA PAYMENT POLLING LOOP STARTED")
    logger.info("   Interval: %s seconds", interval)
    logger.info("=" * 50)
    while True:
        try:
            expired_pending = await subs_storage.get_expired_pending(timeout_minutes=30)
            for sub in expired_pending:
                if sub.payment_gateway != "platega":
                    continue
                await subs_storage.cancel_pending(sub.user_id)
                language = await telegram.get_language(sub.user_id)
                await telegram.send_message(
                    sub.user_id,
                    "⏰ Ссылка на оплату истекла.\n\nВремя на оплату истекло (30 минут). Создайте новый счёт."
                    if language == "ru"
                    else "⏰ Payment link expired.\n\nPayment time expired (30 minutes). Create a new invoice.",
                )

            pending = await subs_storage.get_pending_invoices()
            for sub in pending:
                if sub.payment_gateway != "platega":
                    continue
                if sub.payment_hash is None:
                    continue
                txn = await platega_client.get_payment_status(sub.payment_hash)
                if txn is not None and txn.status == "CONFIRMED":
                    plan_days = subs_storage.get_plan_days(sub.plan)
                    expires_at = int(time.time()) + plan_days * 86400
                    await subs_storage.activate(
                        user_id=sub.user_id,
                        plan=sub.plan,
                        invoice_id=sub.invoice_id or 0,
                        payment_hash=sub.payment_hash,
                        paid_amount=str(txn.amount),
                        paid_asset=txn.currency,
                        expires_at=expires_at,
                    )
                    language = await telegram.get_language(sub.user_id)
                    from datetime import datetime
                    expires_str = datetime.fromtimestamp(expires_at).strftime("%d.%m.%Y %H:%M")
                    await telegram.send_message(
                        sub.user_id,
                        f"✅ Оплата через СБП подтверждена!\n\n📦 {sub.plan} дней\n⏰ До: {expires_str}",
                    )
        except Exception:
            logger.exception("Platega payment polling error")
        await asyncio.sleep(interval)


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
    logger.info("   CryptoBot token: %s...%s", settings.cryptobot_api_token[:5], settings.cryptobot_api_token[-5:] if len(settings.cryptobot_api_token) > 5 else "N/A")
    logger.info("   Platega merchant: %s...", settings.platega_merchant_id[:8] if settings.platega_merchant_id else "N/A")

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
    subs_storage = SubscriptionStorage(db)
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

    # ── 5b. CryptoBot Client ────────────────────────────────────
    logger.info("─" * 40)
    logger.info("STEP 5b/7: Starting CryptoBot client...")
    crypto_client: CryptoPayClient | None = None
    if settings.cryptobot_api_token:
        crypto_client = CryptoPayClient(settings.cryptobot_api_token)
        await crypto_client.start()
        logger.info("✅ CryptoBot client started")
    else:
        logger.info("⚠️  CRYPTOBOT_API_TOKEN is empty — CryptoBot payments disabled")

    # ── 5c. Platega Client ──────────────────────────────────────
    logger.info("─" * 40)
    logger.info("STEP 5c/7: Starting Platega client...")
    platega_client: PlategaClient | None = None
    if settings.platega_merchant_id and settings.platega_secret:
        platega_client = PlategaClient(settings.platega_merchant_id, settings.platega_secret)
        await platega_client.start()
        logger.info("✅ Platega client started (merchant %s...)", settings.platega_merchant_id[:8])
    else:
        logger.info("⚠️  PLATEGA_MERCHANT_ID/PLATEGA_SECRET empty — Platega payments disabled")

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
        subs_storage=subs_storage,
        crypto_client=crypto_client,
        platega_client=platega_client,
    )
    watcher = MercariWatcher(settings, url_storage, telegram, client, devices, subs_storage, settings.admin_user_ids)

    handlers = make_handlers(url_storage, watcher, telegram, settings.admin_user_ids, subs_storage)
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

    # ── Background: invoice polling ──────────────────────────────
    invoice_poll_task: asyncio.Task[None] | None = None
    platega_poll_task: asyncio.Task[None] | None = None
    expiry_task: asyncio.Task[None] | None = None
    if crypto_client is not None:
        invoice_poll_task = asyncio.create_task(
            _poll_invoices_loop(crypto_client, subs_storage, telegram),
        )
        logger.info("✅ Invoice polling started (interval: 30s)")

    if crypto_client is not None or platega_client is not None:
        expiry_task = asyncio.create_task(
            _expire_subscriptions_loop(subs_storage, url_storage),
        )
        logger.info("✅ Subscription expiry checker started (interval: 10min)")

    if platega_client is not None:
        platega_poll_task = asyncio.create_task(
            _poll_platega_loop(platega_client, subs_storage, telegram),
        )
        logger.info("✅ Platega payment polling started (interval: 30s)")

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

        if invoice_poll_task:
            logger.info("  • Stopping invoice polling...")
            invoice_poll_task.cancel()
            try:
                await invoice_poll_task
            except asyncio.CancelledError:
                pass
            logger.info("  ✅ Invoice polling stopped")
        if expiry_task:
            logger.info("  • Stopping expiry checker...")
            expiry_task.cancel()
            try:
                await expiry_task
            except asyncio.CancelledError:
                pass
            logger.info("  ✅ Expiry checker stopped")

        if crypto_client:
            logger.info("  • Closing CryptoBot client...")
            await crypto_client.close()
            logger.info("  ✅ CryptoBot client closed")

        if platega_poll_task:
            logger.info("  • Stopping Platega payment polling...")
            platega_poll_task.cancel()
            try:
                await platega_poll_task
            except asyncio.CancelledError:
                pass
            logger.info("  ✅ Platega payment polling stopped")
        if platega_client:
            logger.info("  • Closing Platega client...")
            await platega_client.close()
            logger.info("  ✅ Platega client closed")

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
