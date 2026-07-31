import logging
from typing import Any

from models.item import Item

logger = logging.getLogger(__name__)

ITEM_CONTAINER_KEYS = ("items", "entities", "searchResults", "results")
ITEM_ID_KEYS = ("id", "itemId", "item_id")
ITEM_TITLE_KEYS = ("name", "title", "itemName")
ITEM_PRICE_KEYS = ("price", "itemPrice")
ITEM_STATUS_KEYS = ("status", "itemStatus", "saleStatus", "state")


def parse_items(data: dict[str, Any]) -> list[Item]:
    raw_items = _extract_item_list(data)
    logger.info("📦 Raw API response: %s top-level keys, %s raw item entries found",
                len(data), len(raw_items))

    parsed: list[Item] = []
    skipped = 0

    for raw in raw_items:
        item = _parse_single_item(raw)
        if item is not None:
            parsed.append(item)
        else:
            skipped += 1

    if skipped:
        logger.warning("⚠️  Skipped %s malformed item(s) during parsing", skipped)

    logger.info("✅ Parsed %s valid items from %s raw entries", len(parsed), len(raw_items))
    return parsed


def _extract_item_list(data: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ITEM_CONTAINER_KEYS:
        value = data.get(key)
        if isinstance(value, list):
            return [entry for entry in value if isinstance(entry, dict)]

    nested = data.get("data")
    if isinstance(nested, dict):
        return _extract_item_list(nested)

    logger.warning("Could not find items in API response keys: %s", list(data.keys()))
    return []


def _parse_single_item(raw: dict[str, Any]) -> Item | None:
    item_id = _pick_str(raw, ITEM_ID_KEYS)
    title = _pick_str(raw, ITEM_TITLE_KEYS)
    price = _pick_int(raw, ITEM_PRICE_KEYS)
    status = _pick_str(raw, ITEM_STATUS_KEYS) or "unknown"

    if not item_id or not title or price is None:
        logger.debug("Skipping malformed item payload: %s", raw)
        return None

    return Item.from_raw(
        item_id=item_id,
        title=title,
        price=price,
        status=status,
    )


def _pick_str(data: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _pick_int(data: dict[str, Any], keys: tuple[str, ...]) -> int | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            cleaned = value.replace(",", "").strip()
            try:
                return int(float(cleaned))
            except (ValueError, OverflowError):
                continue
    return None
