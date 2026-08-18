import json
from decimal import Decimal, InvalidOperation
from typing import Any


PLAN_PAYMENTS: dict[str, tuple[Decimal, str]] = {
    "7d": (Decimal("100"), "RUB"),
    "30d": (Decimal("300"), "RUB"),
}


def payment_matches(
    plan: str,
    user_id: str,
    amount: Any,
    asset: str | None,
    payload: str | None,
    *,
    currency: str,
    expected_asset: str,
) -> bool:
    expected = PLAN_PAYMENTS.get(plan)
    if expected is None:
        return False
    expected_amount, expected_currency = expected
    try:
        actual_amount = Decimal(str(amount))
    except (InvalidOperation, TypeError, ValueError):
        return False
    if actual_amount != expected_amount:
        return False
    if (asset or "").upper() != expected_asset.upper():
        return False
    if currency.upper() != expected_currency:
        return False
    if not payload:
        return False
    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(data, dict):
        return False
    try:
        plan_days = int(data.get("plan", 0))
    except (TypeError, ValueError):
        return False
    return data.get("user_id") == user_id and plan_days == int(plan.rstrip("d"))
