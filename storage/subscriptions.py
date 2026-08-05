import time
import logging
from dataclasses import dataclass
from typing import Any

from storage.connection import DatabaseConnection

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SubscriptionRow:
    user_id: str
    plan: str
    status: str
    subscribed_at: int | None
    expires_at: int | None
    invoice_id: int | None
    payment_hash: str | None
    paid_amount: str | None
    paid_asset: str | None
    created_at: int
    updated_at: int


class SubscriptionStorage:

    def __init__(self, db: DatabaseConnection) -> None:
        self._db = db

    async def get_active(self, user_id: str) -> SubscriptionRow | None:
        cursor = await self._db.conn.execute(
            "SELECT * FROM subscriptions WHERE user_id = ? AND status = 'active' AND expires_at > ?",
            (user_id, int(time.time())),
        )
        row = await cursor.fetchone()
        return await self._row_to_subscription(row) if row else None

    async def get_any(self, user_id: str) -> SubscriptionRow | None:
        cursor = await self._db.conn.execute(
            "SELECT * FROM subscriptions WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
        return await self._row_to_subscription(row) if row else None

    async def create(self, user_id: str, plan: str, invoice_id: int) -> None:
        now = int(time.time())
        async with self._db.transaction() as conn:
            await conn.execute(
                "INSERT INTO subscriptions (user_id, plan, status, invoice_id, created_at, updated_at) "
                "VALUES (?, ?, 'pending', ?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET "
                "  plan = excluded.plan,"
                "  status = 'pending',"
                "  invoice_id = excluded.invoice_id,"
                "  updated_at = excluded.updated_at",
                (user_id, plan, invoice_id, now, now),
            )
        logger.info("📝 Subscription pending for user %s (plan=%s, invoice=%s)", user_id, plan, invoice_id)

    async def activate(
        self,
        user_id: str,
        plan: str,
        invoice_id: int,
        payment_hash: str,
        paid_amount: str,
        paid_asset: str,
        expires_at: int,
    ) -> None:
        now = int(time.time())
        async with self._db.transaction() as conn:
            await conn.execute(
                "UPDATE subscriptions SET "
                "  status = 'active',"
                "  subscribed_at = ?,"
                "  expires_at = ?,"
                "  payment_hash = ?,"
                "  paid_amount = ?,"
                "  paid_asset = ?,"
                "  updated_at = ? "
                "WHERE user_id = ? AND invoice_id = ?",
                (now, expires_at, payment_hash, paid_amount, paid_asset, now, user_id, invoice_id),
            )
        logger.info("✅ Subscription activated for user %s (plan=%s, expires=%s)", user_id, plan, expires_at)

    async def mark_expired(self, user_id: str) -> None:
        now = int(time.time())
        async with self._db.transaction() as conn:
            await conn.execute(
                "UPDATE subscriptions SET status = 'expired', updated_at = ? "
                "WHERE user_id = ? AND status = 'active'",
                (now, user_id),
            )
        logger.info("⏰ Subscription marked expired for user %s", user_id)

    async def get_all_expired_active(self) -> list[SubscriptionRow]:
        now = int(time.time())
        cursor = await self._db.conn.execute(
            "SELECT * FROM subscriptions WHERE status = 'active' AND expires_at <= ?",
            (now,),
        )
        rows = await cursor.fetchall()
        result: list[SubscriptionRow] = []
        for r in rows:
            sub = await self._row_to_subscription(r)
            if sub:
                result.append(sub)
        return result

    async def get_pending_invoices(self) -> list[SubscriptionRow]:
        cursor = await self._db.conn.execute(
            "SELECT * FROM subscriptions WHERE status = 'pending'",
        )
        rows = await cursor.fetchall()
        result: list[SubscriptionRow] = []
        for r in rows:
            sub = await self._row_to_subscription(r)
            if sub:
                result.append(sub)
        return result

    async def get_active_count(self) -> int:
        now = int(time.time())
        cursor = await self._db.conn.execute(
            "SELECT COUNT(*) FROM subscriptions WHERE status = 'active' AND expires_at > ?",
            (now,),
        )
        row = await cursor.fetchone()
        return row[0] if row else 0

    async def is_subscribed(self, user_id: str) -> bool:
        return await self.get_active(user_id) is not None

    async def has_used_trial(self, user_id: str) -> bool:
        cursor = await self._db.conn.execute(
            "SELECT 1 FROM trial_usages WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
        return row is not None

    async def activate_trial(self, user_id: str, expires_at: int) -> None:
        now = int(time.time())
        async with self._db.transaction() as conn:
            await conn.execute(
                "INSERT OR IGNORE INTO trial_usages (user_id, used_at) VALUES (?, ?)",
                (user_id, now),
            )
            await conn.execute(
                "INSERT INTO subscriptions (user_id, plan, status, subscribed_at, expires_at, created_at, updated_at) "
                "VALUES (?, 'trial', 'active', ?, ?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET "
                "  plan = 'trial',"
                "  status = 'active',"
                "  subscribed_at = excluded.subscribed_at,"
                "  expires_at = excluded.expires_at,"
                "  updated_at = excluded.updated_at",
                (user_id, now, expires_at, now, now),
            )
        logger.info("🎁 Trial activated for user %s (expires=%s)", user_id, expires_at)

    @staticmethod
    async def _row_to_subscription(row: Any) -> SubscriptionRow | None:
        if row is None:
            return None
        return SubscriptionRow(
            user_id=row["user_id"],
            plan=row["plan"],
            status=row["status"],
            subscribed_at=row["subscribed_at"],
            expires_at=row["expires_at"],
            invoice_id=row["invoice_id"],
            payment_hash=row["payment_hash"],
            paid_amount=row["paid_amount"],
            paid_asset=row["paid_asset"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
