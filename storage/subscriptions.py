import logging
import re
import secrets
import sqlite3
import string
import time
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
    expiry_reminder_sent: int | None
    promo_extended: int
    created_at: int
    updated_at: int


@dataclass(slots=True, frozen=True)
class PromoCodeRow:
    id: int
    code: str
    duration_days: int
    audience: str
    target_user_id: str | None
    active: bool
    expires_at: int | None
    created_by: str
    created_at: int
    redeemed_by: str | None
    redeemed_at: int | None


@dataclass(slots=True, frozen=True)
class PromoRedemptionResult:
    success: bool
    reason: str
    duration_days: int = 0
    expires_at: int | None = None


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

    async def create(
        self,
        user_id: str,
        plan: str,
        invoice_id: int,
        payment_gateway: str = "cryptobot",
        payment_hash: str | None = None,
    ) -> None:
        now = int(time.time())
        async with self._db.transaction() as conn:
            await conn.execute(
                "INSERT INTO subscriptions (user_id, plan, status, invoice_id, payment_hash, payment_gateway, created_at, updated_at) "
                "VALUES (?, ?, 'pending', ?, ?, ?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET "
                "  plan = excluded.plan,"
                "  status = 'pending',"
                "  invoice_id = excluded.invoice_id,"
                "  payment_hash = excluded.payment_hash,"
                "  payment_gateway = excluded.payment_gateway,"
                "  created_at = excluded.created_at,"
                "  updated_at = excluded.updated_at",
                (user_id, plan, invoice_id, payment_hash, payment_gateway, now, now),
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
    ) -> bool:
        now = int(time.time())
        async with self._db.transaction() as conn:
            prev_cursor = await conn.execute(
                "SELECT plan, expires_at, promo_extended FROM subscriptions "
                "WHERE user_id = ? AND invoice_id = ? AND status = 'pending'",
                (user_id, invoice_id),
            )
            prev = await prev_cursor.fetchone()
            was_active = (
                prev is not None
                and prev["expires_at"] is not None
                and prev["expires_at"] > now
            )
            keep_promo = (
                was_active
                and prev["promo_extended"] is not None
                and int(prev["promo_extended"]) == 1
            )
            cursor = await conn.execute(
                "UPDATE subscriptions SET "
                "  status = 'active',"
                "  subscribed_at = ?,"
                "  expires_at = ?,"
                "  payment_hash = ?,"
                "  paid_amount = ?,"
                "  paid_asset = ?,"
                "  expiry_reminder_sent = NULL,"
                "  promo_extended = ?,"
                "  updated_at = ? "
                "WHERE user_id = ? AND invoice_id = ? AND status = 'pending'",
                (now, expires_at, payment_hash, paid_amount, paid_asset, int(keep_promo), now, user_id, invoice_id),
            )
            if cursor.rowcount > 0:
                await conn.execute(
                    "INSERT INTO users (chat_id, language, ever_paid, created_at, updated_at) "
                    "VALUES (?, 'ru', 1, ?, ?) "
                    "ON CONFLICT(chat_id) DO UPDATE SET "
                    "  ever_paid = 1,"
                    "  updated_at = excluded.updated_at",
                    (user_id, now, now),
                )
        activated = cursor.rowcount > 0
        if activated:
            logger.info("✅ Subscription activated for user %s (plan=%s, expires=%s)", user_id, plan, expires_at)
        else:
            logger.info("ℹ️ Subscription activation skipped for user %s (invoice=%s is no longer pending)", user_id, invoice_id)
        return activated

    async def mark_expired(self, user_id: str, expected_expires_at: int | None = None) -> bool:
        now = int(time.time())
        async with self._db.transaction() as conn:
            sql = (
                "UPDATE subscriptions SET status = 'expired', updated_at = ? "
                "WHERE user_id = ? AND status = 'active'"
            )
            params: tuple[object, ...] = (now, user_id)
            if expected_expires_at is not None:
                sql += " AND expires_at <= ? AND expires_at = ?"
                params += (now, expected_expires_at)
            cursor = await conn.execute(sql, params)
        logger.info("⏰ Subscription marked expired for user %s: %s", user_id, cursor.rowcount > 0)
        return cursor.rowcount > 0

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

    async def get_expiring_soon(self, seconds: int = 86400) -> list[SubscriptionRow]:
        """Активные подписки, которым осталось не больше `seconds` (напоминание ещё не слали).

        Trial-подписки исключены: они длятся всего 12 часов, и текст
        «остался 1 день» для них неверен.
        """
        now = int(time.time())
        cursor = await self._db.conn.execute(
            "SELECT * FROM subscriptions WHERE status = 'active' "
            "AND plan != 'trial' "
            "AND expires_at > ? AND expires_at <= ? "
            "AND (expiry_reminder_sent IS NULL OR expiry_reminder_sent = 0)",
            (now, now + seconds),
        )
        rows = await cursor.fetchall()
        result: list[SubscriptionRow] = []
        for r in rows:
            sub = await self._row_to_subscription(r)
            if sub:
                result.append(sub)
        return result

    async def mark_expiry_reminder_sent(self, user_id: str, expected_expires_at: int | None = None) -> bool:
        now = int(time.time())
        async with self._db.transaction() as conn:
            sql = (
                "UPDATE subscriptions SET expiry_reminder_sent = ? "
                "WHERE user_id = ? AND status = 'active' AND expires_at > ?"
            )
            params: tuple[object, ...] = (now, user_id, now)
            if expected_expires_at is not None:
                sql += " AND expires_at = ?"
                params += (expected_expires_at,)
            cursor = await conn.execute(sql, params)
        logger.info("🔔 Expiry reminder marked sent for user %s: %s", user_id, cursor.rowcount > 0)
        return cursor.rowcount > 0

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

    async def cancel_pending(
        self,
        user_id: str,
        invoice_id: int | None = None,
        payment_gateway: str | None = None,
    ) -> bool:
        """Отменяет неоплаченный счёт.

        Если у пользователя был активный доступ (expires_at ещё в будущем),
        статус восстанавливается в 'active': начало покупки не должно
        отнимать уже оплаченные/промо-дни при отказе от оплаты.
        """
        now = int(time.time())
        async with self._db.transaction() as conn:
            sql = (
                "UPDATE subscriptions SET "
                "  status = CASE WHEN expires_at > ? THEN 'active' ELSE 'expired' END, "
                "  updated_at = ? "
                "WHERE user_id = ? AND status = 'pending'"
            )
            params: tuple[object, ...] = (now, now, user_id)
            if invoice_id is not None:
                sql += " AND invoice_id = ?"
                params += (invoice_id,)
            if payment_gateway is not None:
                sql += " AND payment_gateway = ?"
                params += (payment_gateway,)
            cursor = await conn.execute(sql, params)
        logger.info("⏰ Pending subscription cancelled for user %s: %s", user_id, cursor.rowcount > 0)
        return cursor.rowcount > 0

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
        cursor = await self._db.conn.execute(
            "SELECT 1 FROM subscriptions "
            "WHERE user_id = ? AND status IN ('active', 'pending') AND expires_at > ?",
            (user_id, int(time.time())),
        )
        return await cursor.fetchone() is not None

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
            current_cursor = await conn.execute(
                "SELECT status FROM subscriptions WHERE user_id = ?", (user_id,),
            )
            current = await current_cursor.fetchone()
            if current is not None and current["status"] == "pending":
                logger.warning("⚠️ Trial blocked for user %s because payment is pending", user_id)
                return False
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
                "  invoice_id = NULL,"
                "  payment_hash = NULL,"
                "  paid_amount = NULL,"
                "  paid_asset = NULL,"
                "  payment_gateway = NULL,"
                "  expiry_reminder_sent = NULL,"
                "  promo_extended = 0,"
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

    # ── Promo codes ──────────────────────────────────────────────

    @staticmethod
    def normalize_promo_code(raw_code: str) -> str:
        return raw_code.strip().upper()

    @staticmethod
    def validate_custom_promo_code(raw_code: str) -> str:
        """Normalize and validate a custom promo code; raise ValueError if invalid."""
        code = SubscriptionStorage.normalize_promo_code(raw_code)
        if not re.fullmatch(r"[A-Z0-9-]{1,32}", code):
            raise ValueError("Invalid custom promo code")
        return code

    @staticmethod
    def _generate_promo_code() -> str:
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        return "MERCARI-" + "".join(secrets.choice(alphabet) for _ in range(8))

    async def create_promo(
        self,
        duration_days: int,
        audience: str,
        created_by: str,
        *,
        target_user_id: str | None = None,
        expires_at: int | None = None,
        custom_code: str | None = None,
    ) -> PromoCodeRow:
        """Create a single-use promo code and return the generated code."""
        if duration_days <= 0:
            raise ValueError("Promo duration must be positive")
        if audience not in {"all", "new_only"}:
            raise ValueError("Unsupported promo audience")

        now = int(time.time())
        if expires_at is not None and expires_at <= now:
            raise ValueError("Promo expiration must be in the future")
        target = target_user_id.strip() if target_user_id and target_user_id.strip() else None

        async with self._db.transaction() as conn:
            if custom_code is not None:
                candidate = self.validate_custom_promo_code(custom_code)
                try:
                    cursor = await conn.execute(
                        "INSERT INTO promo_codes "
                        "(code, duration_days, audience, target_user_id, active, expires_at, created_by, created_at) "
                        "VALUES (?, ?, ?, ?, 1, ?, ?, ?)",
                        (candidate, duration_days, audience, target, expires_at, created_by, now),
                    )
                except sqlite3.IntegrityError as exc:
                    raise ValueError("Promo code already exists") from exc
                promo_id = int(cursor.lastrowid)
            else:
                for _ in range(10):
                    candidate = self.normalize_promo_code(self._generate_promo_code())
                    try:
                        cursor = await conn.execute(
                            "INSERT INTO promo_codes "
                            "(code, duration_days, audience, target_user_id, active, expires_at, created_by, created_at) "
                            "VALUES (?, ?, ?, ?, 1, ?, ?, ?)",
                            (candidate, duration_days, audience, target, expires_at, created_by, now),
                        )
                    except sqlite3.IntegrityError:
                        continue
                    promo_id = int(cursor.lastrowid)
                    break
                else:
                    raise RuntimeError("Failed to generate a unique promo code")

        logger.info(
            "🎟 Promo code created: code=%s, days=%s, audience=%s, target=%s, by=%s",
            candidate, duration_days, audience, target or "-", created_by,
        )
        return PromoCodeRow(
            id=promo_id,
            code=candidate,
            duration_days=duration_days,
            audience=audience,
            target_user_id=target,
            active=True,
            expires_at=expires_at,
            created_by=created_by,
            created_at=now,
            redeemed_by=None,
            redeemed_at=None,
        )

    async def list_promos(self) -> list[PromoCodeRow]:
        cursor = await self._db.conn.execute(
            "SELECT p.id, p.code, p.duration_days, p.audience, p.target_user_id, "
            "p.active, p.expires_at, p.created_by, p.created_at, "
            "r.user_id AS redeemed_by, r.redeemed_at "
            "FROM promo_codes p "
            "LEFT JOIN promo_redemptions r ON r.promo_id = p.id "
            "ORDER BY p.created_at DESC, p.id DESC",
        )
        rows = await cursor.fetchall()
        return [
            PromoCodeRow(
                id=row["id"],
                code=row["code"],
                duration_days=row["duration_days"],
                audience=row["audience"],
                target_user_id=row["target_user_id"],
                active=bool(row["active"]),
                expires_at=row["expires_at"],
                created_by=row["created_by"],
                created_at=row["created_at"],
                redeemed_by=row["redeemed_by"],
                redeemed_at=row["redeemed_at"],
            )
            for row in rows
        ]

    async def deactivate_promo(self, raw_code: str) -> bool:
        code = self.normalize_promo_code(raw_code)
        async with self._db.transaction() as conn:
            cursor = await conn.execute(
                "UPDATE promo_codes SET active = 0 WHERE code = ? AND active = 1",
                (code,),
            )
            changed = cursor.rowcount > 0
        if changed:
            logger.info("🎟 Promo code deactivated: %s", code)
        return changed

    async def redeem_promo(self, user_id: str, raw_code: str) -> PromoRedemptionResult:
        """Atomically validate, consume and apply a single-use promo code."""
        code = self.normalize_promo_code(raw_code)
        if not code:
            return PromoRedemptionResult(False, "not_found")

        now = int(time.time())
        async with self._db.transaction() as conn:
            cursor = await conn.execute(
                "SELECT p.*, r.user_id AS redeemed_by "
                "FROM promo_codes p "
                "LEFT JOIN promo_redemptions r ON r.promo_id = p.id "
                "WHERE p.code = ?",
                (code,),
            )
            promo = await cursor.fetchone()
            if promo is None:
                return PromoRedemptionResult(False, "not_found")
            if not promo["active"]:
                return PromoRedemptionResult(False, "inactive")
            if promo["redeemed_by"] is not None:
                return PromoRedemptionResult(False, "used")
            if promo["expires_at"] is not None and promo["expires_at"] <= now:
                return PromoRedemptionResult(False, "expired")
            if promo["target_user_id"] is not None and promo["target_user_id"] != user_id:
                return PromoRedemptionResult(False, "target")

            user_cursor = await conn.execute(
                "SELECT ever_paid FROM users WHERE chat_id = ?",
                (user_id,),
            )
            user = await user_cursor.fetchone()
            ever_paid = bool(user["ever_paid"]) if user is not None else False

            if promo["audience"] == "new_only":
                if ever_paid:
                    return PromoRedemptionResult(False, "already_paid")
                previous_cursor = await conn.execute(
                    "SELECT 1 FROM promo_redemptions r "
                    "JOIN promo_codes p ON p.id = r.promo_id "
                    "WHERE r.user_id = ? AND p.audience = 'new_only' LIMIT 1",
                    (user_id,),
                )
                if await previous_cursor.fetchone() is not None:
                    return PromoRedemptionResult(False, "new_promo_used")

            sub_cursor = await conn.execute(
                "SELECT plan, status, expires_at FROM subscriptions WHERE user_id = ?",
                (user_id,),
            )
            subscription = await sub_cursor.fetchone()
            if subscription is not None and subscription["status"] == "pending":
                return PromoRedemptionResult(False, "pending")

            base = now
            if subscription is not None and subscription["expires_at"] and subscription["expires_at"] > now:
                base = subscription["expires_at"]
            expires_at = base + int(promo["duration_days"]) * 86400

            inserted = await conn.execute(
                "INSERT OR IGNORE INTO promo_redemptions (promo_id, user_id, redeemed_at) "
                "VALUES (?, ?, ?)",
                (promo["id"], user_id, now),
            )
            if inserted.rowcount == 0:
                return PromoRedemptionResult(False, "used")

            await conn.execute(
                "INSERT OR IGNORE INTO users (chat_id, language, ever_paid, created_at, updated_at) "
                "VALUES (?, 'ru', 0, ?, ?)",
                (user_id, now, now),
            )

            if subscription is None:
                await conn.execute(
                    "INSERT INTO subscriptions "
                    "(user_id, plan, status, subscribed_at, expires_at, promo_extended, created_at, updated_at) "
                    "VALUES (?, 'promo', 'active', ?, ?, 0, ?, ?)",
                    (user_id, now, expires_at, now, now),
                )
            else:
                await conn.execute(
                    "UPDATE subscriptions SET "
                    "plan = CASE "
                    "  WHEN plan IN ('trial', 'promo') THEN 'promo' "
                    "  WHEN expires_at IS NULL THEN 'promo' "
                    "  WHEN expires_at <= ? THEN 'promo' "
                    "  ELSE plan END, "
                    "promo_extended = CASE "
                    "  WHEN plan NOT IN ('trial', 'promo') "
                    "       AND expires_at IS NOT NULL AND expires_at > ? THEN 1 "
                    "  ELSE 0 END, "
                    "status = 'active', expires_at = ?, "
                    "expiry_reminder_sent = NULL, updated_at = ? WHERE user_id = ?",
                    (now, now, expires_at, now, user_id),
                )

        logger.info(
            "🎟 Promo code redeemed: code=%s, user=%s, days=%s, expires=%s",
            code, user_id, promo["duration_days"], expires_at,
        )
        return PromoRedemptionResult(
            True,
            "success",
            duration_days=int(promo["duration_days"]),
            expires_at=expires_at,
        )

    async def get_stats(self) -> dict:
        """Агрегаты для админ-панели: статусы, планы, выручка, whitelist."""
        by_status: dict[str, int] = {}
        cursor = await self._db.conn.execute(
            "SELECT status, COUNT(*) AS n FROM subscriptions GROUP BY status"
        )
        for row in await cursor.fetchall():
            by_status[row["status"]] = row["n"]

        by_plan: dict[str, int] = {}
        cursor = await self._db.conn.execute(
            "SELECT plan, COUNT(*) AS n FROM subscriptions "
            "WHERE status IN ('pending', 'active') GROUP BY plan"
        )
        for row in await cursor.fetchall():
            by_plan[row["plan"]] = row["n"]

        promo_users: int = 0
        cursor = await self._db.conn.execute(
            "SELECT COUNT(*) AS n FROM subscriptions "
            "WHERE status = 'active' AND expires_at > ? "
            "AND (plan = 'promo' OR promo_extended = 1)",
            (int(time.time()),),
        )
        row = await cursor.fetchone()
        if row:
            promo_users = int(row["n"] or 0)

        revenue: dict[str, float] = {}
        cursor = await self._db.conn.execute(
            "SELECT paid_asset, SUM(CAST(paid_amount AS REAL)) AS total "
            "FROM subscriptions WHERE status = 'active' AND paid_amount IS NOT NULL "
            "AND paid_amount != '' GROUP BY paid_asset"
        )
        for row in await cursor.fetchall():
            if row["paid_asset"]:
                revenue[row["paid_asset"]] = float(row["total"] or 0.0)

        cursor = await self._db.conn.execute("SELECT COUNT(*) AS n FROM whitelist")
        whitelist_row = await cursor.fetchone()

        return {
            "by_status": by_status,
            "by_plan": by_plan,
            "promo_users": promo_users,
            "revenue": revenue,
            "whitelist": whitelist_row["n"] if whitelist_row else 0,
        }

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
            expiry_reminder_sent=row["expiry_reminder_sent"],
            promo_extended=int(row["promo_extended"] or 0),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
