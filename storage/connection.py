import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import aiosqlite

logger = logging.getLogger(__name__)

CREATE_TABLE_ITEMS_SQL = """
CREATE TABLE IF NOT EXISTS items (
    item_id TEXT NOT NULL,
    search_url_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    price INTEGER NOT NULL,
    status TEXT NOT NULL,
    url TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (item_id, search_url_id)
);
"""

CREATE_TABLE_URLS_SQL = """
CREATE TABLE IF NOT EXISTS search_urls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    name TEXT NOT NULL,
    user_chat_id TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    added_at INTEGER NOT NULL,
    source TEXT NOT NULL DEFAULT 'url',
    UNIQUE(url, user_chat_id)
);
"""

CREATE_TABLE_SEEN_ITEMS_SQL = """
CREATE TABLE IF NOT EXISTS seen_items (
    item_id TEXT NOT NULL,
    search_url_id INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (item_id, search_url_id)
);
"""

CREATE_INDEX_SEEN_ITEMS_SQL = """
CREATE INDEX IF NOT EXISTS idx_seen_items_url_id ON seen_items(search_url_id);
"""

CREATE_TABLE_NOTIFICATION_OUTBOX_SQL = """
CREATE TABLE IF NOT EXISTS notification_outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id TEXT NOT NULL,
    search_url_id INTEGER NOT NULL,
    chat_id TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    UNIQUE (item_id, search_url_id)
);
"""

CREATE_INDEX_NOTIFICATION_OUTBOX_SQL = """
CREATE INDEX IF NOT EXISTS idx_notification_outbox_created_at
ON notification_outbox(created_at);
"""

# Per-user device_uuid: каждый пользователь бота представляется Mercari
# как отдельное устройство со своим UUID и своим EC-ключом DPoP.
# Раньше DEVICE_UUID был один на весь процесс (общая «личность» для всех юзеров).
CREATE_TABLE_USER_DEVICES_SQL = """
CREATE TABLE IF NOT EXISTS user_devices (
    user_chat_id TEXT PRIMARY KEY,
    device_uuid TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
"""

CREATE_TABLE_USERS_SQL = """
CREATE TABLE IF NOT EXISTS users (
    chat_id TEXT PRIMARY KEY,
    language TEXT NOT NULL DEFAULT 'ru' CHECK (language IN ('ru', 'en')),
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
"""

# Existing users are discovered from the tables that already contain their
# chat IDs. They keep the requested default language: Russian.
MIGRATE_EXISTING_USERS_SQL = """
INSERT OR IGNORE INTO users (chat_id, language, created_at, updated_at)
SELECT user_chat_id, 'ru', CAST(strftime('%s', 'now') AS INTEGER), CAST(strftime('%s', 'now') AS INTEGER)
FROM search_urls
UNION
SELECT user_chat_id, 'ru', CAST(strftime('%s', 'now') AS INTEGER), CAST(strftime('%s', 'now') AS INTEGER)
FROM user_devices
UNION
SELECT chat_id, 'ru', CAST(strftime('%s', 'now') AS INTEGER), CAST(strftime('%s', 'now') AS INTEGER)
FROM notification_outbox;
"""

MIGRATE_DEACTIVATED_AT_SQL = """
ALTER TABLE search_urls ADD COLUMN deactivated_at INTEGER;
"""

MIGRATE_URL_SOURCE_SQL = """
ALTER TABLE search_urls ADD COLUMN source TEXT NOT NULL DEFAULT 'url';
"""

# Существующие строки созданы до колонки source — размечаем старым
# эвристиком (по наличию параметра keyword в URL).
BACKFILL_URL_SOURCE_SQL = """
UPDATE search_urls SET source = 'keyword' WHERE url LIKE '%keyword=%';
"""

MIGRATE_PAYMENT_GATEWAY_SQL = """
ALTER TABLE subscriptions ADD COLUMN payment_gateway TEXT DEFAULT 'cryptobot';
"""

MIGRATE_EXPIRY_REMINDER_SENT_SQL = """
ALTER TABLE subscriptions ADD COLUMN expiry_reminder_sent INTEGER;
"""

CREATE_TABLE_SUBSCRIPTIONS_SQL = """
CREATE TABLE IF NOT EXISTS subscriptions (
    user_id       TEXT PRIMARY KEY,
    plan          TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'active', 'expired', 'cancelled')),
    subscribed_at INTEGER,
    expires_at    INTEGER,
    invoice_id    INTEGER,
    payment_hash  TEXT,
    paid_amount   TEXT,
    paid_asset    TEXT,
    created_at    INTEGER NOT NULL DEFAULT (unixepoch()),
    updated_at    INTEGER NOT NULL DEFAULT (unixepoch())
);
"""

CREATE_TABLE_TRIAL_USAGES_SQL = """
CREATE TABLE IF NOT EXISTS trial_usages (
    user_id TEXT PRIMARY KEY,
    used_at INTEGER NOT NULL
);
"""

CREATE_TABLE_WHITELIST_SQL = """
CREATE TABLE IF NOT EXISTS whitelist (
    user_id    TEXT PRIMARY KEY,
    granted_by TEXT NOT NULL,
    granted_at INTEGER NOT NULL
);
"""


class DatabaseConnection:
    """Manages async SQLite connection and schema creation."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None
        # Сериализует критические секции: при параллельных asyncio.gather
        # только одна корутина владеет транзакцией в каждый момент времени,
        # иначе commit одной фиксировал бы незавершённую работу другой.
        self._tx_lock = asyncio.Lock()

    async def connect(self) -> None:
        logger.info("⏳ Connecting to database: %s", self._db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        # isolation_level=None → настоящий autocommit на уровне sqlite3:
        # DML не открывает неявную транзакцию. Транзакциями управляем явно
        # через transaction() (BEGIN/COMMIT/ROLLBACK). Это критично, потому
        # при legacy-режиме (isolation_level='') commit одной корутины
        # фиксировал бы незавершённую работу другой на том же соединении.
        self._conn = await aiosqlite.connect(self._db_path, isolation_level=None)
        self._conn.row_factory = aiosqlite.Row
        logger.debug("  • Setting PRAGMA journal_mode=WAL...")
        await self._conn.execute("PRAGMA journal_mode=WAL;")
        logger.debug("  • Setting PRAGMA busy_timeout=5000...")
        await self._conn.execute("PRAGMA busy_timeout=5000;")
        logger.debug("  • Creating table: items...")
        await self._conn.execute(CREATE_TABLE_ITEMS_SQL)
        logger.debug("  • Creating table: search_urls...")
        await self._conn.execute(CREATE_TABLE_URLS_SQL)
        logger.debug("  • Creating table: seen_items...")
        await self._conn.execute(CREATE_TABLE_SEEN_ITEMS_SQL)
        logger.debug("  • Creating table: notification_outbox...")
        await self._conn.execute(CREATE_TABLE_NOTIFICATION_OUTBOX_SQL)
        await self._conn.execute(CREATE_TABLE_USER_DEVICES_SQL)
        logger.debug("  • Creating table: users...")
        await self._conn.execute(CREATE_TABLE_USERS_SQL)
        await self._conn.execute(MIGRATE_EXISTING_USERS_SQL)
        logger.debug("  • Creating table: subscriptions...")
        await self._conn.execute(CREATE_TABLE_SUBSCRIPTIONS_SQL)
        logger.debug("  • Creating table: trial_usages...")
        await self._conn.execute(CREATE_TABLE_TRIAL_USAGES_SQL)
        logger.debug("  • Creating table: whitelist...")
        await self._conn.execute(CREATE_TABLE_WHITELIST_SQL)
        logger.debug("  • Creating index: idx_seen_items_url_id...")
        await self._conn.execute(CREATE_INDEX_SEEN_ITEMS_SQL)
        logger.debug("  • Creating index: idx_notification_outbox_created_at...")
        await self._conn.execute(CREATE_INDEX_NOTIFICATION_OUTBOX_SQL)
        logger.debug("  • Running migration: deactivated_at column...")
        try:
            await self._conn.execute(MIGRATE_DEACTIVATED_AT_SQL)
        except Exception:
            logger.debug("  • deactivated_at column already exists — skipping")
        logger.debug("  • Running migration: source column...")
        try:
            await self._conn.execute(MIGRATE_URL_SOURCE_SQL)
        except Exception:
            logger.debug("  • source column already exists — skipping")
        else:
            logger.debug("  • Backfilling source for existing URLs...")
            await self._conn.execute(BACKFILL_URL_SOURCE_SQL)
        logger.debug("  • Running migration: payment_gateway column...")
        try:
            await self._conn.execute(MIGRATE_PAYMENT_GATEWAY_SQL)
        except Exception:
            logger.debug("  • payment_gateway column already exists — skipping")
        logger.debug("  • Running migration: expiry_reminder_sent column...")
        try:
            await self._conn.execute(MIGRATE_EXPIRY_REMINDER_SENT_SQL)
        except Exception:
            logger.debug("  • expiry_reminder_sent column already exists — skipping")
        await self._conn.commit()
        logger.info("=" * 50)
        logger.info("🗄️  DATABASE CONNECTED")
        logger.info("   Path: %s", self._db_path)
        logger.info("   Mode: WAL (Write-Ahead Logging)")
        logger.info("   Tables: items, search_urls, seen_items, users, subscriptions, trial_usages, whitelist")
        logger.info("=" * 50)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[aiosqlite.Connection]:
        """Атомарная критическая секция для параллельных корутин.

        Один экземпляр Connection разделяется между всеми корутинами watcher'а
        (asyncio.gather). Без явной блокировки commit корутины A мог бы
        зафиксировать незавершённые изменения корутины B, работающей с тем же
        соединением. Этот менеджер:
          - берёт lock (один владелец транзакции за раз);
          - явно открывает BEGIN и COMMIT/ROLLBACK;
          - отпускает lock в finally.
        Вызывайте тяжёлую сеть (Telegram, Mercari) ВНЕ этого блока.
        """
        if self._conn is None:
            raise RuntimeError("Database is not connected")
        async with self._tx_lock:
            logger.debug("🔒 DB transaction: BEGIN (lock acquired)")
            await self._conn.execute("BEGIN")
            try:
                yield self._conn
                await self._conn.execute("COMMIT")
                logger.debug("🔓 DB transaction: COMMIT (lock released)")
            except BaseException as exc:
                logger.warning("⚠️  DB transaction: ROLLBACK due to %s: %s", type(exc).__name__, exc)
                await self._conn.execute("ROLLBACK")
                raise

    async def close(self) -> None:
        if self._conn is not None:
            logger.info("⏳ Closing database connection...")
            await self._conn.close()
            self._conn = None
            logger.info("=" * 50)
            logger.info("🗄️  DATABASE CONNECTION CLOSED")
            logger.info("=" * 50)
        else:
            logger.debug("DatabaseConnection.close() called but connection was already closed")

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database is not connected")
        return self._conn
