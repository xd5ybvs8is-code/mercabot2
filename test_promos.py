import asyncio
import time

from storage.connection import DatabaseConnection
from storage.subscriptions import SubscriptionStorage
from telegram.handlers import _parse_promo_create_input
from telegram.keyboard import (
    build_plan_selection_keyboard,
    build_subscription_inline_keyboard,
)


def test_promo_code_is_single_use_and_extends_access(tmp_path) -> None:
    asyncio.run(_test_promo_code_is_single_use_and_extends_access(tmp_path))


async def _test_promo_code_is_single_use_and_extends_access(tmp_path) -> None:
    db = DatabaseConnection(tmp_path / "state.db")
    await db.connect()
    storage = SubscriptionStorage(db)

    promo = await storage.create_promo(7, "all", "admin")
    first = await storage.redeem_promo("user-1", promo.code)
    assert first.success is True
    assert first.duration_days == 7

    subscription = await storage.get_any("user-1")
    assert subscription is not None
    assert subscription.plan == "promo"
    assert subscription.promo_extended == 0
    assert subscription.status == "active"
    assert subscription.expires_at is not None
    assert subscription.expires_at >= int(time.time()) + 7 * 86400

    assert (await storage.redeem_promo("user-1", promo.code)).reason == "used"
    assert (await storage.redeem_promo("user-2", promo.code)).reason == "used"

    await db.close()


def test_promo_plan_states(tmp_path) -> None:
    asyncio.run(_test_promo_plan_states(tmp_path))


async def _test_promo_plan_states(tmp_path) -> None:
    db = DatabaseConnection(tmp_path / "state.db")
    await db.connect()
    storage = SubscriptionStorage(db)
    now = int(time.time())

    await storage.create("paid-active", "7d", 1)
    await storage.activate("paid-active", "7d", 1, "hash", "100", "USDT", now + 7 * 86400)
    promo = await storage.create_promo(3, "all", "admin")
    assert (await storage.redeem_promo("paid-active", promo.code)).success is True
    sub = await storage.get_any("paid-active")
    assert sub is not None
    assert sub.plan == "7d"
    assert sub.promo_extended == 1

    await storage.create("paid-active", "7d", 2)
    await storage.activate("paid-active", "7d", 2, "hash2", "100", "USDT", now + 14 * 86400)
    sub = await storage.get_any("paid-active")
    assert sub.plan == "7d"
    assert sub.promo_extended == 1

    await storage.create("paid-expired", "7d", 3)
    await storage.activate("paid-expired", "7d", 3, "hash3", "100", "USDT", now - 1000)
    promo2 = await storage.create_promo(3, "all", "admin")
    assert (await storage.redeem_promo("paid-expired", promo2.code)).success is True
    sub = await storage.get_any("paid-expired")
    assert sub is not None
    assert sub.plan == "promo"
    assert sub.promo_extended == 0

    await db.conn.execute(
        "UPDATE subscriptions SET expires_at = ? WHERE user_id = 'paid-active'",
        (now - 1000,),
    )
    await storage.create("paid-active", "30d", 4)
    await storage.activate("paid-active", "30d", 4, "hash4", "300", "USDT", now + 30 * 86400)
    sub = await storage.get_any("paid-active")
    assert sub is not None
    assert sub.plan == "30d"
    assert sub.promo_extended == 0

    await db.close()


def test_new_user_promo_rules_include_trial_but_exclude_paid_users(tmp_path) -> None:
    asyncio.run(_test_new_user_promo_rules_include_trial_but_exclude_paid_users(tmp_path))


async def _test_new_user_promo_rules_include_trial_but_exclude_paid_users(tmp_path) -> None:
    db = DatabaseConnection(tmp_path / "state.db")
    await db.connect()
    storage = SubscriptionStorage(db)
    now = int(time.time())

    trial_user = "trial-user"
    await storage.activate_trial(trial_user, now + 12 * 3600)
    trial_promo = await storage.create_promo(7, "new_only", "admin")
    assert (await storage.redeem_promo(trial_user, trial_promo.code)).success is True
    trial_subscription = await storage.get_any(trial_user)
    assert trial_subscription is not None
    assert trial_subscription.plan == "promo"

    second_promo = await storage.create_promo(7, "new_only", "admin")
    assert (await storage.redeem_promo(trial_user, second_promo.code)).reason == "new_promo_used"

    paid_user = "paid-user"
    await storage.create(paid_user, "7d", 1)
    await storage.activate(
        paid_user,
        "7d",
        1,
        "payment-hash",
        "100",
        "USDT",
        now + 7 * 86400,
    )
    paid_promo = await storage.create_promo(7, "new_only", "admin")
    assert (await storage.redeem_promo(paid_user, paid_promo.code)).reason == "already_paid"

    user_cursor = await db.conn.execute(
        "SELECT ever_paid FROM users WHERE chat_id = ?", (paid_user,)
    )
    user_row = await user_cursor.fetchone()
    assert user_row["ever_paid"] == 1
    await db.close()


def test_promo_target_expiration_and_deactivation(tmp_path) -> None:
    asyncio.run(_test_promo_target_expiration_and_deactivation(tmp_path))


async def _test_promo_target_expiration_and_deactivation(tmp_path) -> None:
    db = DatabaseConnection(tmp_path / "state.db")
    await db.connect()
    storage = SubscriptionStorage(db)
    now = int(time.time())

    targeted = await storage.create_promo(
        3,
        "all",
        "admin",
        target_user_id="target-user",
        expires_at=now + 3600,
    )
    assert (await storage.redeem_promo("other-user", targeted.code)).reason == "target"
    assert (await storage.redeem_promo("target-user", targeted.code)).success is True

    expired = await storage.create_promo(3, "all", "admin", expires_at=now + 1)
    await asyncio.sleep(1.1)
    assert (await storage.redeem_promo("user", expired.code)).reason == "expired"

    inactive = await storage.create_promo(3, "all", "admin")
    assert await storage.deactivate_promo(inactive.code) is True
    assert (await storage.redeem_promo("user", inactive.code)).reason == "inactive"

    await db.close()


def test_promo_redemption_is_serialized(tmp_path) -> None:
    asyncio.run(_test_promo_redemption_is_serialized(tmp_path))


def test_abandoned_purchase_keeps_active_promo_access(tmp_path) -> None:
    asyncio.run(_test_abandoned_purchase_keeps_active_promo_access(tmp_path))


async def _test_abandoned_purchase_keeps_active_promo_access(tmp_path) -> None:
    db = DatabaseConnection(tmp_path / "state.db")
    await db.connect()
    storage = SubscriptionStorage(db)

    promo = await storage.create_promo(5, "all", "admin")
    assert (await storage.redeem_promo("user-1", promo.code)).success is True
    before = await storage.get_any("user-1")
    assert before is not None and before.status == "active"
    assert before.expires_at is not None

    await storage.create("user-1", "7d", 42)
    pending = await storage.get_any("user-1")
    assert pending is not None and pending.status == "pending"

    await storage.cancel_pending("user-1")
    after = await storage.get_any("user-1")
    assert after is not None
    assert after.status == "active"
    assert after.expires_at == before.expires_at

    await db.close()


def test_cancel_pending_expires_without_future_expiry(tmp_path) -> None:
    asyncio.run(_test_cancel_pending_expires_without_future_expiry(tmp_path))


async def _test_cancel_pending_expires_without_future_expiry(tmp_path) -> None:
    db = DatabaseConnection(tmp_path / "state.db")
    await db.connect()
    storage = SubscriptionStorage(db)
    now = int(time.time())

    await storage.create("new-user", "7d", 1)
    await storage.cancel_pending("new-user")
    assert (await storage.get_any("new-user")).status == "expired"

    await storage.create("old-user", "7d", 2)
    await storage.activate("old-user", "7d", 2, "hash", "100", "USDT", now - 1000)
    await storage.create("old-user", "7d", 3)
    await storage.cancel_pending("old-user")
    assert (await storage.get_any("old-user")).status == "expired"

    await db.close()
async def _test_promo_redemption_is_serialized(tmp_path) -> None:
    db = DatabaseConnection(tmp_path / "state.db")
    await db.connect()
    storage = SubscriptionStorage(db)
    promo = await storage.create_promo(7, "all", "admin")

    results = await asyncio.gather(
        storage.redeem_promo("user-1", promo.code),
        storage.redeem_promo("user-2", promo.code),
    )
    assert sum(result.success for result in results) == 1
    assert sum(result.reason == "used" for result in results) == 1
    await db.close()


def test_promo_custom_code(tmp_path) -> None:
    asyncio.run(_test_promo_custom_code(tmp_path))


async def _test_promo_custom_code(tmp_path) -> None:
    db = DatabaseConnection(tmp_path / "state.db")
    await db.connect()
    storage = SubscriptionStorage(db)

    promo = await storage.create_promo(7, "all", "admin", custom_code="summer2026")
    assert promo.code == "SUMMER2026"

    try:
        await storage.create_promo(7, "all", "admin", custom_code="SUMMER2026")
        assert False, "Duplicate custom code must raise ValueError"
    except ValueError:
        pass

    for bad in ("bad code", "bad!", "", "A" * 33):
        try:
            await storage.create_promo(7, "all", "admin", custom_code=bad)
            assert False, f"Invalid custom code must raise ValueError: {bad!r}"
        except ValueError:
            pass

    auto = await storage.create_promo(7, "all", "admin")
    assert auto.code.startswith("MERCARI-")
    assert (await storage.redeem_promo("user-1", "SUMMER2026")).success is True

    await db.close()


def test_promo_unlimited_multi_use(tmp_path) -> None:
    asyncio.run(_test_promo_unlimited_multi_use(tmp_path))


async def _test_promo_unlimited_multi_use(tmp_path) -> None:
    db = DatabaseConnection(tmp_path / "state.db")
    await db.connect()
    storage = SubscriptionStorage(db)

    promo = await storage.create_promo(7, "all", "admin", max_uses=None)
    assert promo.max_uses is None

    for user in ("user-1", "user-2", "user-3"):
        result = await storage.redeem_promo(user, promo.code)
        assert result.success is True
        sub = await storage.get_any(user)
        assert sub is not None and sub.status == "active"

    assert (await storage.redeem_promo("user-1", promo.code)).reason == "used"

    entries = await storage.list_promos()
    row = next(e for e in entries if e.code == promo.code)
    assert row.redemption_count == 3
    assert row.max_uses is None
    assert {user_id for user_id, _ in row.redeemed_users} == {"user-1", "user-2", "user-3"}

    await db.close()


def test_promo_limited_multi_use(tmp_path) -> None:
    asyncio.run(_test_promo_limited_multi_use(tmp_path))


async def _test_promo_limited_multi_use(tmp_path) -> None:
    db = DatabaseConnection(tmp_path / "state.db")
    await db.connect()
    storage = SubscriptionStorage(db)

    promo = await storage.create_promo(3, "all", "admin", max_uses=2)
    assert promo.max_uses == 2
    assert (await storage.redeem_promo("user-1", promo.code)).success is True
    assert (await storage.redeem_promo("user-2", promo.code)).success is True
    assert (await storage.redeem_promo("user-3", promo.code)).reason == "used"
    assert (await storage.redeem_promo("user-1", promo.code)).reason == "used"

    entries = await storage.list_promos()
    row = next(e for e in entries if e.code == promo.code)
    assert row.redemption_count == 2
    assert {user_id for user_id, _ in row.redeemed_users} == {"user-1", "user-2"}

    await db.close()


def test_promo_max_uses_validation(tmp_path) -> None:
    asyncio.run(_test_promo_max_uses_validation(tmp_path))


async def _test_promo_max_uses_validation(tmp_path) -> None:
    db = DatabaseConnection(tmp_path / "state.db")
    await db.connect()
    storage = SubscriptionStorage(db)

    for bad in (0, -1):
        try:
            await storage.create_promo(7, "all", "admin", max_uses=bad)
            assert False, f"max_uses={bad} must raise ValueError"
        except ValueError:
            pass

    await db.close()


def test_promo_redemptions_composite_pk_migration(tmp_path) -> None:
    asyncio.run(_test_promo_redemptions_composite_pk_migration(tmp_path))


async def _test_promo_redemptions_composite_pk_migration(tmp_path) -> None:
    import aiosqlite

    db_path = tmp_path / "state.db"
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute(
            "CREATE TABLE promo_codes ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL UNIQUE,"
            "duration_days INTEGER NOT NULL, audience TEXT NOT NULL DEFAULT 'all',"
            "target_user_id TEXT, active INTEGER NOT NULL DEFAULT 1,"
            "expires_at INTEGER, created_by TEXT NOT NULL, created_at INTEGER NOT NULL)"
        )
        await conn.execute(
            "CREATE TABLE promo_redemptions ("
            "promo_id INTEGER PRIMARY KEY, user_id TEXT NOT NULL,"
            "redeemed_at INTEGER NOT NULL)"
        )
        await conn.execute(
            "INSERT INTO promo_codes (code, duration_days, audience, active, created_by, created_at)"
            "VALUES ('OLDCODE', 7, 'all', 1, 'admin', 1)"
        )
        await conn.execute(
            "INSERT INTO promo_redemptions (promo_id, user_id, redeemed_at) "
            "VALUES (1, 'old-user', 2)"
        )
        await conn.commit()

    db = DatabaseConnection(db_path)
    await db.connect()
    storage = SubscriptionStorage(db)

    redemption_cols = await db.conn.execute_fetchall(
        "PRAGMA table_info(promo_redemptions)"
    )
    user_id_pk = next(int(row[5]) for row in redemption_cols if row[1] == "user_id")
    assert user_id_pk != 0

    assert (await storage.redeem_promo("old-user", "OLDCODE")).reason == "used"

    promo = await storage.create_promo(3, "all", "admin", max_uses=None)
    assert promo.max_uses is None
    assert (await storage.redeem_promo("new-user-1", promo.code)).success is True
    assert (await storage.redeem_promo("new-user-2", promo.code)).success is True

    row = next(e for e in await storage.list_promos() if e.code == promo.code)
    assert row.redemption_count == 2

    await db.close()


def test_promo_create_input_parser() -> None:
    assert _parse_promo_create_input("7 | new_only | - | -") == (7, "new_only", None, None, None, 1)
    parsed = _parse_promo_create_input("30 | all | 12345 | 2099-12-31")
    assert parsed is not None
    assert parsed[:3] == (30, "all", "12345")
    assert parsed[4] is None
    assert parsed[5] == 1
    assert _parse_promo_create_input("7 | something") is None
    assert _parse_promo_create_input("7 | new_only | bad") is None
    assert _parse_promo_create_input("7 | all | - | - | -") == (7, "all", None, None, None, 1)
    assert _parse_promo_create_input("7 | all | - | - | SUMMER2026") == (7, "all", None, None, "SUMMER2026", 1)
    assert _parse_promo_create_input("7 | all | - | - | summer2026") == (7, "all", None, None, "SUMMER2026", 1)
    assert _parse_promo_create_input("7 | all | - | - | bad code") is None
    assert _parse_promo_create_input("7 | all | - | - | " + "A" * 33) is None
    assert _parse_promo_create_input("7 | all | - | - | - | 50") == (7, "all", None, None, None, 50)
    assert _parse_promo_create_input("7 | all | - | - | - | ∞") == (7, "all", None, None, None, None)
    assert _parse_promo_create_input("7 | all | - | - | - | 0") == (7, "all", None, None, None, None)
    assert _parse_promo_create_input("7 | all | - | - | - | unlimited") == (7, "all", None, None, None, None)
    assert _parse_promo_create_input("7 | all | - | - | - | bad") is None
    assert _parse_promo_create_input("7 | all | - | - | - | -5") is None
    assert _parse_promo_create_input("7 | all | - | - | - | 50 | extra") is None


def test_subscription_screens_include_promo_button() -> None:
    for markup in (build_subscription_inline_keyboard(), build_plan_selection_keyboard()):
        buttons = [button for row in markup["inline_keyboard"] for button in row]
        assert any(button["callback_data"] == "promo_enter" for button in buttons)


def test_promo_delete_frees_code_name(tmp_path) -> None:
    asyncio.run(_test_promo_delete_frees_code_name(tmp_path))


async def _test_promo_delete_frees_code_name(tmp_path) -> None:
    db = DatabaseConnection(tmp_path / "state.db")
    await db.connect()
    storage = SubscriptionStorage(db)

    promo = await storage.create_promo(7, "all", "admin", custom_code="test")
    assert (await storage.redeem_promo("user-1", promo.code)).success is True

    assert await storage.delete_promo(promo.code) is False

    assert await storage.deactivate_promo(promo.code) is True
    assert (await storage.redeem_promo("user-2", promo.code)).reason == "inactive"

    assert await storage.delete_promo(promo.code) is True
    assert await storage.delete_promo(promo.code) is False

    recreated = await storage.create_promo(3, "all", "admin", custom_code="test")
    assert recreated.code == "TEST"
    assert (await storage.redeem_promo("user-3", recreated.code)).success is True

    await db.close()
