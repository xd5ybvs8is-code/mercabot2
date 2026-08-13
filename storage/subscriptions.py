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
    payment_gateway: str | None
    created_at: int
    updated_at: int


class SubscriptionStorage:

    def __init__(self, db: DatabaseConnection) -> None:
        self._db = db

    @staticmethod
    def get_plan_days(plan: str) -> int:
        if plan == "7d":
            return 7
        if plan == "30d":
            return 30
        if plan.endswith("d"):
            return int(plan.rstrip("d"))
        return 30

    async def get_renewal_expiry(self, user_id: str, plan_days: int) -> int:
        """Timestamp of expiry for a renewal.

        Если текущая подписка ещё не истекла, срок плюсуется к её дате
        окончания; иначе отсчитывается от «сейчас». Старый expires_at при
        покупке сохраняется в строке (create() его не трогает), поэтому
        смотрим на get_any, а не на get_active.
        """
        base = int(time.time())
        row = await self.get_any(user_id)
        if row is not None and row.expires_at and row.expires_at > base:
            base = row.expires_at
        return base + plan_days * 86400

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

    async def create(self, user_id: str, plan: str, invoice_id: int, payment_gateway: str = "cryptobot") -> None:
        now = int(time.time())
        async with self._db.transaction() as conn:
            await conn.execute(
                "INSERT INTO subscriptions (user_id, plan, status, invoice_id, payment_gateway, created_at, updated_at) "
                "VALUES (?, ?, 'pending', ?, ?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET "
                "  plan = excluded.plan,"
                "  status = 'pending',"
                "  invoice_id = excluded.invoice_id,"
                "  payment_gateway = excluded.payment_gateway,"
                "  created_at = excluded.created_at,"
                "  updated_at = excluded.updated_at",
                (user_id, plan, invoice_id, payment_gateway, now, now),
            )
        logger.info("📝 Subscription pending for user %s (plan=%s, invoice=%s, gateway=%s)", user_id, plan, invoice_id, payment_gateway)

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

    async def get_expired_pending(self, timeout_minutes: int = 30) -> list[SubscriptionRow]:
        cutoff = int(time.time()) - timeout_minutes * 60
        cursor = await self._db.conn.execute(
            "SELECT * FROM subscriptions WHERE status = 'pending' AND created_at <= ?",
            (cutoff,),
        )
        rows = await cursor.fetchall()
        result: list[SubscriptionRow] = []
        for r in rows:
            sub = await self._row_to_subscription(r)
            if sub:
                result.append(sub)
        return result

    async def cancel_pending(self, user_id: str) -> None:
        now = int(time.time())
        async with self._db.transaction() as conn:
            await conn.execute(
                "UPDATE subscriptions SET status = 'expired', updated_at = ? "
                "WHERE user_id = ? AND status = 'pending'",
                (now, user_id),
            )
        logger.info("⏰ Pending subscription cancelled (expired) for user %s", user_id)

    async def set_payment_hash(self, user_id: str, payment_hash: str) -> None:
        now = int(time.time())
        async with self._db.transaction() as conn:
            await conn.execute(
                "UPDATE subscriptions SET payment_hash = ?, updated_at = ? "
                "WHERE user_id = ? AND status = 'pending'",
                (payment_hash, now, user_id),
            )
        logger.info("🔑 Payment hash set for user %s: %s", user_id, payment_hash)

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

    async def count_all(self) -> int:
        """Total subscriptions (pending + active)."""
        cursor = await self._db.conn.execute(
            "SELECT COUNT(*) FROM subscriptions WHERE status IN ('pending', 'active')",
        )
        row = await cursor.fetchone()
        return row[0] if row else 0

    async def has_used_trial(self, user_id: str) -> bool:
        cursor = await self._db.conn.execute(
            "SELECT 1 FROM trial_usages WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
        return row is not None

    async def activate_trial(self, user_id: str, expires_at: int) -> bool:
        now = int(time.time())
        async with self._db.transaction() as conn:
            cursor = await conn.execute(
                "INSERT OR IGNORE INTO trial_usages (user_id, used_at) VALUES (?, ?)",
                (user_id, now),
            )
            if cursor.rowcount == 0:
                logger.warning("⚠️  Trial already used by user %s — activation blocked", user_id)
                return False
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
        return True

    async def whitelist_add(self, user_id: str, granted_by: str) -> bool:
        now = int(time.time())
        async with self._db.transaction() as conn:
            cursor = await conn.execute(
                "INSERT OR IGNORE INTO whitelist (user_id, granted_by, granted_at) VALUES (?, ?, ?)",
                (user_id, granted_by, now),
            )
            added = cursor.rowcount > 0
        if added:
            logger.info("👤 Whitelisted user %s (granted by %s)", user_id, granted_by)
        else:
            logger.info("👤 User %s already whitelisted", user_id)
        return added

    async def whitelist_remove(self, user_id: str) -> bool:
        async with self._db.transaction() as conn:
            cursor = await conn.execute(
                "DELETE FROM whitelist WHERE user_id = ?",
                (user_id,),
            )
            removed = cursor.rowcount > 0
        if removed:
            logger.info("👤 Removed user %s from whitelist", user_id)
        return removed

    async def whitelist_list(self) -> list[tuple[str, str, int]]:
        cursor = await self._db.conn.execute(
            "SELECT user_id, granted_by, granted_at FROM whitelist ORDER BY granted_at DESC",
        )
        rows = await cursor.fetchall()
        return [(r["user_id"], r["granted_by"], r["granted_at"]) for r in rows]

    async def is_whitelisted(self, user_id: str) -> bool:
        cursor = await self._db.conn.execute(
            "SELECT 1 FROM whitelist WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
        return row is not None

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
            payment_gateway=row["payment_gateway"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
