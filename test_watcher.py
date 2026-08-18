import asyncio

from mercari.watcher import MercariWatcher
from models.item import Item
from storage.urls import SearchUrlRow

URL_A = "https://jp.mercari.com/en/search?keyword=a"
URL_B = "https://jp.mercari.com/en/search?keyword=b"


def _row(url_id: int, url: str, user: str) -> SearchUrlRow:
    return SearchUrlRow(
        id=url_id,
        url=url,
        name=url,
        user_chat_id=user,
        active=True,
        added_at=0,
        source="url",
    )


def test_group_by_url() -> None:
    rows = [
        _row(1, URL_A, "u1"),
        _row(2, URL_A, "u2"),
        _row(3, URL_B, "u3"),
    ]
    groups = MercariWatcher._group_by_url(rows)

    assert set(groups) == {URL_A, URL_B}
    assert [r.id for r in groups[URL_A]] == [1, 2]
    assert [r.id for r in groups[URL_B]] == [3]


def test_fetch_and_process_group_dedups_search() -> None:
    asyncio.run(_test_fetch_and_process_group_dedups_search())


async def _test_fetch_and_process_group_dedups_search() -> None:
    rows = [_row(1, URL_A, "u1"), _row(2, URL_A, "u2")]

    class FakeDevices:
        async def get_signer(self, user_chat_id):
            return object()

    class FakeClient:
        def __init__(self):
            self.calls = 0

        async def search(self, condition, dpop=None):
            self.calls += 1
            return [Item.from_raw("m1", "t", 100, "on_sale")]

    watcher = object.__new__(MercariWatcher)
    watcher._semaphore = asyncio.Semaphore(10)
    watcher._devices = FakeDevices()
    watcher._client = FakeClient()

    processed = []

    async def fake_process(items, ids, row):
        processed.append(row.id)

    watcher._process_new_items = fake_process

    await watcher._fetch_and_process_group(rows)

    assert watcher._client.calls == 1
    assert processed == [1, 2]
