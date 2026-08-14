import logging
import time
from typing import NamedTuple

from storage.connection import DatabaseConnection

logger = logging.getLogger(__name__)


class SearchUrlRow(NamedTuple):
    id: int
    url: str
    name: str
    user_chat_id: str
    active: bool
    added_at: int


class PendingNotification(NamedTuple):
    id: int
    item_id: str
    search_url_id: int
    chat_id: str
    text: str


class UrlStorage:
    """CRUD operations for search_urls, seen_items, items, and outbox tables.

    Контекст транзакций: методы БД-записи не делают commit сами —
    их фиксирует DatabaseConnection.transaction(), в который их оборачивает
    вызывающий код (см. MercariWatcher). Методы только на чтение
    (get_*, count_*, has_urls, is_url_bootstrapped) тоже могут вызываться
    как внутри, так и вне transaction(): в autocommit-режиме SELECT
    выполняется без транзакции.
    """

    def __init__(self, db: DatabaseConnection) -> None:
        self._db = db

    @property
    def conn(self):
        return self._db.conn

    def transaction(self):
        """Прокси к DatabaseConnection.transaction() для удобства."""
        return self._db.transaction()

    # ── search_urls ──────────────────────────────────────────────

    async def add(self, url: str, user_chat_id: str, name: str | None = None) -> tuple[bool, int]:
        """Add URL for user. Returns (was_new, id).

        Оборачивает INSERT в собственную transaction(): это точечная
        операция из обработчика команды Telegram, вне цикла watcher'а.
        """
        if not name:
            name = url
        logger.info("📝 Adding URL: user=%s, name='%s', url=%s", user_chat_id, name, url[:80])
        async with self._db.transaction() as conn:
            try:
                cursor = await conn.execute(
                    "INSERT INTO search_urls (url, name, user_chat_id, active, added_at) VALUES (?, ?, ?, 1, ?)",
                    (url, name, user_chat_id, int(time.time())),
                )
                logger.info("✅ URL added successfully: id=%s, name='%s'", cursor.lastrowid, name)
                return True, cursor.lastrowid
            except Exception:
                row = await conn.execute(
                    "SELECT id FROM search_urls WHERE url = ? AND user_chat_id = ?",
                    (url, user_chat_id),
                )
                existing = await row.fetchone()
                if existing is None:
                    logger.error("❌ Failed to add URL (unexpected error)")
                    raise
                logger.info("ℹ️  URL already exists for this user: id=%s", existing[0])
                return False, existing[0]

    async def remove(self, url_id: int, user_chat_id: str) -> bool:
        logger.info("🗑️ Removing URL: id=%s, user=%s", url_id, user_chat_id)
        async with self._db.transaction() as conn:
            cursor = await conn.execute(
                "DELETE FROM search_urls WHERE id = ? AND user_chat_id = ?",
                (url_id, user_chat_id),
            )
            if cursor.rowcount > 0:
                await conn.execute(
                    "DELETE FROM notification_outbox WHERE search_url_id = ?",
                    (url_id,),
                )
                logger.info("✅ URL #%s removed successfully", url_id)
            else:
                logger.warning("⚠️  URL #%s not found or not owned by user %s", url_id, user_chat_id)
            return cursor.rowcount > 0

    async def get_active_urls(self) -> list[SearchUrlRow]:
        rows = await self.conn.execute_fetchall(
            "SELECT id, url, name, user_chat_id, active, added_at FROM search_urls WHERE active = 1 ORDER BY id"
        )
        logger.debug("📋 get_active_urls: %s active URL(s) found", len(rows))
        return [SearchUrlRow(*row) for row in rows]

    async def get_user_urls(self, user_chat_id: str) -> list[SearchUrlRow]:
        rows = await self.conn.execute_fetchall(
            "SELECT id, url, name, user_chat_id, active, added_at FROM search_urls WHERE user_chat_id = ? ORDER BY id",
            (user_chat_id,),
        )
        logger.debug("📋 get_user_urls(%s): %s URL(s) found", user_chat_id, len(rows))
        return [SearchUrlRow(*row) for row in rows]

    async def get_all_user_chat_ids(self) -> set[str]:
        rows = await self.conn.execute_fetchall(
            "SELECT DISTINCT user_chat_id FROM search_urls WHERE active = 1"
        )
        chat_ids = {row[0] for row in rows}
        logger.debug("👥 get_all_user_chat_ids: %s unique user(s)", len(chat_ids))
        return chat_ids

    async def has_urls(self) -> bool:
        cursor = await self.conn.execute(
            "SELECT 1 FROM search_urls WHERE active = 1 LIMIT 1"
        )
        row = await cursor.fetchone()
        result = row is not None
        logger.debug("🔍 has_urls: %s", result)
        return result

    async def rename(self, url_id: int, user_chat_id: str, name: str) -> bool:
        logger.info("✏️  Renaming URL #%s for user %s to '%s'", url_id, user_chat_id, name)
        async with self._db.transaction() as conn:
            cursor = await conn.execute(
                "UPDATE search_urls SET name = ? WHERE id = ? AND user_chat_id = ?",
                (name, url_id, user_chat_id),
            )
            if cursor.rowcount > 0:
                logger.info("✅ URL #%s renamed to '%s'", url_id, name)
            else:
                logger.warning("⚠️  URL #%s not found or not owned by user %s", url_id, user_chat_id)
            return cursor.rowcount > 0

    # ── items (statistics) ────────────────────────────────────

    async def count_items(self, search_url_id: int) -> int:
        cursor = await self.conn.execute(
            "SELECT COUNT(*) FROM items WHERE search_url_id = ?", (search_url_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else 0

    async def insert_items_bulk(self, search_url_id: int, items: list) -> None:
        """Insert items into the items table (for /stats). Uses INSERT OR IGNORE.

        Фиксацию вызывает вызывающий код (transaction() в watcher'е),
        чтобы запись items и пометка seen были атомарны относительно других URL.
        """
        if not items:
            return
        now = int(time.time())
        rows = [
            (item.id, search_url_id, item.title, item.price, item.status, item.url, now)
            for item in items
        ]
        await self.conn.executemany(
            "INSERT OR IGNORE INTO items (item_id, search_url_id, title, price, status, url, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )

    # ── seen_items ──────────────────────────────────────────────

    async def is_url_bootstrapped(self, search_url_id: int) -> bool:
        """True if this URL has any seen_items recorded.

        Used as a persistent "bootstrap done" flag: once a URL has been
        fetched at least once, seen_items is non-empty and stays non-empty,
        so a process restart won't re-bootstrap it (and thus swallow fresh
        listings as "already seen").
        """
        cursor = await self.conn.execute(
            "SELECT 1 FROM seen_items WHERE search_url_id = ? LIMIT 1",
            (search_url_id,),
        )
        row = await cursor.fetchone()
        return row is not None

    async def get_seen_ids(self, search_url_id: int) -> set[str]:
        """Return all known item_ids for a given search URL."""
        rows = await self.conn.execute_fetchall(
            "SELECT item_id FROM seen_items WHERE search_url_id = ?",
            (search_url_id,),
        )
        return {row[0] for row in rows}

    async def mark_seen_bulk(self, search_url_id: int, item_ids: list[str]) -> None:
        """Mark items as seen (INSERT OR IGNORE).

        Фиксацию вызывает вызывающий код (transaction() в watcher'е).
        """
        if not item_ids:
            return
        now = int(time.time())
        rows = [(item_id, search_url_id, now) for item_id in item_ids]
        await self.conn.executemany(
            "INSERT OR IGNORE INTO seen_items (item_id, search_url_id, created_at) VALUES (?, ?, ?)",
            rows,
        )

    # ── notification outbox ───────────────────────────────────────

    async def add_pending_notification(
        self,
        search_url_id: int,
        item_id: str,
        chat_id: str,
        text: str,
    ) -> PendingNotification | None:
        """Persist a notification before putting it into the in-memory queue.

        Returns the newly-created row, or ``None`` when this item is already
        pending. The unique key prevents repeated watcher cycles from adding
        duplicate messages while Telegram is unavailable.
        """
        async with self._db.transaction() as conn:
            cursor = await conn.execute(
                "INSERT OR IGNORE INTO notification_outbox "
                "(item_id, search_url_id, chat_id, text, created_at) VALUES (?, ?, ?, ?, ?)",
                (item_id, search_url_id, chat_id, text, int(time.time())),
            )
            if cursor.rowcount == 0:
                return None
            notification_id = cursor.lastrowid
            return PendingNotification(
                notification_id, item_id, search_url_id, chat_id, text,
            )

    async def get_pending_notifications(self) -> list[PendingNotification]:
        rows = await self.conn.execute_fetchall(
            "SELECT id, item_id, search_url_id, chat_id, text "
            "FROM notification_outbox ORDER BY id"
        )
        return [PendingNotification(*row) for row in rows]

    async def complete_notification(
        self,
        notification_id: int,
        search_url_id: int,
        item_id: str,
    ) -> None:
        """Atomically acknowledge delivery and mark the item as seen."""
        async with self._db.transaction() as conn:
            await conn.execute(
                "INSERT OR IGNORE INTO seen_items (item_id, search_url_id, created_at) "
                "VALUES (?, ?, ?)",
                (item_id, search_url_id, int(time.time())),
            )
            await conn.execute(
                "DELETE FROM notification_outbox WHERE id = ? AND item_id = ? AND search_url_id = ?",
                (notification_id, item_id, search_url_id),
            )

    # ── cleanup ──────────────────────────────────────────────────

    async def deactivate_chat(self, chat_id: str) -> None:
        """Deactivate all URLs and remove pending notifications for a lost chat."""
        now = int(time.time())
        async with self._db.transaction() as conn:
            await conn.execute(
                "UPDATE search_urls SET active = 0, deactivated_at = ? WHERE user_chat_id = ?",
                (now, chat_id),
            )
            await conn.execute(
                "DELETE FROM notification_outbox WHERE chat_id = ?",
                (chat_id,),
            )
        logger.info(
            "🧹 Cleaned up lost chat %s: deactivated URLs, removed pending notifications",
            chat_id,
        )

    async def reactivate_chat(self, chat_id: str) -> int:
        """Reactivate URLs for a returning user. Returns count of reactivated URLs."""
        async with self._db.transaction() as conn:
            cursor = await conn.execute(
                "UPDATE search_urls SET active = 1, deactivated_at = NULL WHERE user_chat_id = ? AND active = 0",
                (chat_id,),
            )
            count = cursor.rowcount
        if count > 0:
            logger.info(
                "🔄 Reactivated %s URL(s) for returning user %s",
                count, chat_id,
            )
        return count

    async def cleanup_deactivated_urls(self, max_age_seconds: int) -> int:
        """Hard-delete URLs deactivated longer than max_age_seconds.

        Returns count of deleted URL rows.
        """
        cutoff = int(time.time()) - max_age_seconds
        async with self._db.transaction() as conn:
            cursor = await conn.execute(
                "DELETE FROM search_urls WHERE active = 0 AND deactivated_at IS NOT NULL AND deactivated_at < ?",
                (cutoff,),
            )
            count = cursor.rowcount
        if count > 0:
            logger.info(
                "🧹 Hard-deleted %s URL(s) deactivated longer than %s days",
                count, max_age_seconds // 86400,
            )
        return count

    async def cleanup_old_items(self, max_age_seconds: int) -> tuple[int, int]:
        """Delete records older than max_age_seconds from items and seen_items.

        Returns (deleted_items_count, deleted_seen_count).
        """
        cutoff = int(time.time()) - max_age_seconds
        async with self._db.transaction() as conn:
            cursor = await conn.execute(
                "DELETE FROM items WHERE created_at < ?", (cutoff,)
            )
            items_count = cursor.rowcount
            cursor = await conn.execute(
                "DELETE FROM seen_items WHERE created_at < ?", (cutoff,)
            )
            seen_count = cursor.rowcount
        return items_count, seen_count

    async def get_stats(self) -> dict:
        """Агрегаты для админ-панели: URL, items, seen, outbox."""
        day_start = int(time.time()) - int(time.time()) % 86400

        async def _count(sql: str, params: tuple = ()) -> int:
            cursor = await self.conn.execute(sql, params)
            row = await cursor.fetchone()
            return row[0] if row else 0

        stats = {
            "urls_total": await _count("SELECT COUNT(*) FROM search_urls"),
            "urls_active": await _count(
                "SELECT COUNT(*) FROM search_urls WHERE active = 1"
            ),
            "items_total": await _count("SELECT COUNT(*) FROM items"),
            "items_today": await _count(
                "SELECT COUNT(*) FROM items WHERE created_at >= ?", (day_start,)
            ),
            "seen_total": await _count("SELECT COUNT(*) FROM seen_items"),
            "outbox": await _count("SELECT COUNT(*) FROM notification_outbox"),
        }
        return stats
