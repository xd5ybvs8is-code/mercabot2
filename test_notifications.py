import asyncio

from storage.connection import DatabaseConnection
from storage.urls import SearchUrlRow, UrlStorage
from telegram.messages import format_url_detail
from telegram.sender import MessageSender, _FAILED, _OK


def test_notification_outbox_survives_restart(tmp_path) -> None:
    asyncio.run(_test_notification_outbox_survives_restart(tmp_path))


async def _test_notification_outbox_survives_restart(tmp_path) -> None:
    db_path = tmp_path / "state.db"
    db = DatabaseConnection(db_path)
    await db.connect()
    storage = UrlStorage(db)

    pending = await storage.add_pending_notification(7, "item-1", "chat-1", "text")
    assert pending is not None
    assert await storage.get_seen_ids(7) == set()
    assert await storage.add_pending_notification(7, "item-1", "chat-1", "text") is None
    await db.close()

    db = DatabaseConnection(db_path)
    await db.connect()
    storage = UrlStorage(db)
    restored = await storage.get_pending_notifications()
    assert [(row.item_id, row.chat_id, row.text) for row in restored] == [
        ("item-1", "chat-1", "text"),
    ]

    await storage.complete_notification(restored[0].id, 7, "item-1")
    assert await storage.get_pending_notifications() == []
    assert await storage.get_seen_ids(7) == {"item-1"}
    await db.close()


def test_sender_acknowledges_only_successful_delivery() -> None:
    asyncio.run(_test_sender_acknowledges_only_successful_delivery())


async def _test_sender_acknowledges_only_successful_delivery() -> None:
    class FakeClient:
        def __init__(self, result: bool) -> None:
            self.result = result
            self.calls = 0

        async def call_api(self, _method, _payload) -> bool:
            self.calls += 1
            return self.result

    acknowledged = 0

    async def acknowledge() -> None:
        nonlocal acknowledged
        acknowledged += 1

    success_client = FakeClient(True)
    success_sender = MessageSender(success_client, rate_per_sec=1, chat_min_interval=0)
    success_sender.enqueue("chat", "text", show_keyboard=False, on_success=acknowledge)
    result = await success_sender._send_one(success_sender._queue.get_nowait())
    assert result == _OK
    assert success_client.calls == 1
    assert acknowledged == 1

    failure_client = FakeClient(False)
    failure_sender = MessageSender(failure_client, rate_per_sec=1, chat_min_interval=0)
    failure_sender.enqueue("chat", "text", show_keyboard=False, on_success=acknowledge)
    result = await failure_sender._send_one(failure_sender._queue.get_nowait())
    assert result == _FAILED
    assert acknowledged == 1
    assert failure_sender._queue.qsize() == 1


def test_url_detail_escapes_html_user_data() -> None:
    row = SearchUrlRow(
        1,
        "https://jp.mercari.com/en/search?keyword=a&sort=created_time",
        "A <b> & C",
        "chat-1",
        True,
        0,
    )

    text = asyncio.run(format_url_detail(row))

    assert "<b>A &lt;b&gt; &amp; C</b>" in text
    assert "keyword=a&amp;sort=created_time" in text
