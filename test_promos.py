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
    assert subscription.status == "active"
    assert subscription.expires_at is not None
    assert subscription.expires_at >= int(time.time()) + 7 * 86400

    assert (await storage.redeem_promo("user-1", promo.code)).reason == "used"
    assert (await storage.redeem_promo("user-2", promo.code)).reason == "used"

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


def test_promo_create_input_parser() -> None:
    assert _parse_promo_create_input("7 | new_only | - | -") == (7, "new_only", None, None)
    parsed = _parse_promo_create_input("30 | all | 12345 | 2099-12-31")
    assert parsed is not None
    assert parsed[:3] == (30, "all", "12345")
    assert _parse_promo_create_input("7 | something") is None
    assert _parse_promo_create_input("7 | new_only | bad") is None


def test_subscription_screens_include_promo_button() -> None:
    for markup in (build_subscription_inline_keyboard(), build_plan_selection_keyboard()):
        buttons = [button for row in markup["inline_keyboard"] for button in row]
        assert any(button["callback_data"] == "promo_enter" for button in buttons)
