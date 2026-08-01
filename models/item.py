import re
from dataclasses import dataclass

MERCARI_ITEM_URL = "https://jp.mercari.com/item/{item_id}"
SHOP_PRODUCT_URL = "https://jp.mercari.com/en/shops/product/{item_id}"

_ITEM_ID_RE = re.compile(r"^m\d+$")


def get_item_url(item_id: str) -> str:
    template = MERCARI_ITEM_URL if _ITEM_ID_RE.match(item_id) else SHOP_PRODUCT_URL
    return template.format(item_id=item_id)


@dataclass(frozen=True, slots=True)
class Item:
    id: str
    title: str
    price: int
    status: str
    url: str

    @classmethod
    def from_raw(cls, item_id: str, title: str, price: int, status: str) -> "Item":
        return cls(
            id=item_id,
            title=title,
            price=price,
            status=status,
            url=get_item_url(item_id),
        )
