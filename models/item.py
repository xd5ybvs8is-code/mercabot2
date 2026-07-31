from dataclasses import dataclass

MERCARI_ITEM_URL = "https://jp.mercari.com/item/{item_id}"


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
            url=MERCARI_ITEM_URL.format(item_id=item_id),
        )
