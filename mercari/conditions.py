"""Поисковые условия Mercari: парсинг URL пользователя → тело API-запроса.

Mercari exposeит поиск двумя способами:
- URL страницы:  https://jp.mercari.com/en/search?brand_id=7572&sort=created_time
- API-тело:      {searchCondition: {brandId:[7572], sort:"SORT_CREATED_TIME", ...}}

Этот модуль связывает первое со вторым. Поддерживаются только основные
параметры (см. PLAN): brand_id, category_id, keyword, sort, order,
price_min, price_max. Прочие фильтры Mercari здесь не разбираются — их
пользователь может добавить позже расширением _FIELD_MAPPERS.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlparse, urlencode, urlunparse

logger = logging.getLogger(__name__)

# ── Маппинги значений URL → enum-строки API ──────────────────────────────
# Mercari в URL использует короткие имена; в API — UPPER_SNAKE.
SORT_MAP: dict[str, str] = {
    "created_time": "SORT_CREATED_TIME",
    "price": "SORT_PRICE",
    "updated": "SORT_UPDATED_TIME",
}
ORDER_MAP: dict[str, str] = {
    "desc": "ORDER_DESC",
    "asc": "ORDER_ASC",
}
DEFAULT_SORT = "SORT_CREATED_TIME"
DEFAULT_ORDER = "ORDER_DESC"


@dataclass(frozen=True, slots=True)
class SearchCondition:
    """Распарсенное поисковое условие. Все поля опциональны."""

    brand_id: int | None = None
    category_id: int | None = None
    keyword: str = ""
    sort: str = DEFAULT_SORT
    order: str = DEFAULT_ORDER
    price_min: int = 0
    price_max: int = 0

    def to_payload(self, device_uuid: str, page_size: int = 30) -> dict[str, Any]:
        """Тело POST-запроса к api.mercari.jp/v2/entities:search.

        Формат зафиксирован в ходе экспериментов: searchSessionId может быть
        любой непустой константой (сервер не валидирует значение).
        with*-флаги взяты из реального запроса браузера — они влияют только
        на полноту ответа, не на авторизацию.
        """
        sc = self._search_condition()
        return {
            "userId": "",
            "config": {"responseToggles": ["QUERY_SUGGESTION_WEB_1"]},
            "pageSize": page_size,
            "pageToken": "",
            # Константа — эксперимент (тест A4) показал, что значение произвольно.
            "searchSessionId": "mercabot-session-001",
            "source": "BaseSerp",
            "indexRouting": "INDEX_ROUTING_UNSPECIFIED",
            "thumbnailTypes": [],
            "searchCondition": sc,
            "serviceFrom": "suruga",
            "withItemBrand": True,
            "withItemSize": False,
            "withItemPromotions": True,
            "withItemSizes": True,
            "withShopname": False,
            "useDynamicAttribute": True,
            "withSuggestedItems": True,
            "withOfferPricePromotion": True,
            "withProductSuggest": True,
            "withParentProducts": False,
            "withProductArticles": True,
            "withSearchConditionId": False,
            "withAuction": True,
            "laplaceDeviceUuid": device_uuid,
        }

    def _search_condition(self) -> dict[str, Any]:
        """Блок searchCondition в формате API.

        Поля-списки (brandId, categoryId) — всегда списки, даже если один
        элемент: так требует схема API (экспериментально подтверждено).
        """
        brand_ids: list[int] = [self.brand_id] if self.brand_id else []
        category_ids: list[int] = [self.category_id] if self.category_id else []
        return {
            "keyword": self.keyword,
            "excludeKeyword": "",
            "sort": self.sort,
            "order": self.order,
            "status": [],
            "sizeId": [],
            "categoryId": category_ids,
            "brandId": brand_ids,
            "sellerId": [],
            "priceMin": self.price_min,
            "priceMax": self.price_max,
            "itemConditionId": [],
            "shippingPayerId": [],
            "shippingFromArea": [],
            "shippingMethod": [],
            "colorId": [],
            "hasCoupon": False,
            "attributes": [],
            "itemTypes": [],
            "skuIds": [],
            "shopIds": [],
            "excludeShippingMethodIds": [],
        }


def parse_search_url(url: str) -> SearchCondition:
    """Разбирает поисковый URL Mercari в SearchCondition.

    Принимает и /en/search, и /search — фронт Mercari использует оба.
    Молча игнорирует неизвестные параметры (фильтры, которые мы не поддерживаем).
    """
    parsed = urlparse(url.strip())

    valid_search_paths = ("/search", "/en/search")
    if parsed.path.rstrip("/") not in valid_search_paths:
        raise ValueError(
            f"This is not a Mercari search URL. "
            f"Expected path like /search or /en/search, got: {parsed.path}"
        )

    qs = parse_qs(parsed.query)

    logger.info("🔗 Parsing search URL: %s", url[:120])
    logger.debug("   Query parameters: %s", dict(qs))

    def _first_int(key: str) -> int | None:
        values = qs.get(key)
        if not values:
            return None
        try:
            return int(values[0])
        except ValueError:
            return None

    def _first_str(key: str) -> str:
        values = qs.get(key)
        return values[0].strip() if values else ""

    raw_sort = _first_str("sort")
    raw_order = _first_str("order")

    condition = SearchCondition(
        brand_id=_first_int("brand_id"),
        category_id=_first_int("category_id"),
        keyword=_first_str("keyword"),
        sort=SORT_MAP.get(raw_sort, DEFAULT_SORT),
        order=ORDER_MAP.get(raw_order, DEFAULT_ORDER),
        price_min=_first_int("price_min") or 0,
        price_max=_first_int("price_max") or 0,
    )

    logger.info(
        "✅ Parsed search condition: keyword='%s', brand=%s, category=%s, "
        "price=%s-%s, sort=%s, order=%s",
        condition.keyword or "(none)",
        condition.brand_id or "(any)",
        condition.category_id or "(any)",
        condition.price_min or 0,
        condition.price_max or 0,
        condition.sort,
        condition.order,
    )
    return condition


def normalize_search_url(url: str) -> str:
    """Ensure sort=created_time and order=desc in the URL query string.

    If sort/order are missing — adds them.
    If sort/order are present but different — overwrites them.
    All other query parameters (including unknown ones) are preserved as-is.
    """
    parsed = urlparse(url.strip())
    qs = parse_qs(parsed.query, keep_blank_values=True)
    qs["sort"] = ["created_time"]
    qs["order"] = ["desc"]
    new_query = urlencode(qs, doseq=True)
    return urlunparse(parsed._replace(query=new_query))
