import asyncio
import time

from storage.connection import DatabaseConnection
from storage.subscriptions import SubscriptionStorage
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
        "url",
    )

    text = asyncio.run(format_url_detail(row))

    assert "<b>A &lt;b&gt; &amp; C</b>" in text
    assert "keyword=a&amp;sort=created_time" in text


def test_url_detail_source_label() -> None:
    def make_row(source: str) -> SearchUrlRow:
        return SearchUrlRow(
            1,
            "https://jp.mercari.com/en/search?keyword=a&sort=created_time",
            "kw",
            "chat-1",
            True,
            0,
            source,
        )

    keyword_text = asyncio.run(format_url_detail(make_row("keyword")))
    assert "ключевому слову" in keyword_text

    url_text = asyncio.run(format_url_detail(make_row("url")))
    assert "прямой ссылке" in url_text


def test_expiry_reminder_flow(tmp_path) -> None:
    asyncio.run(_test_expiry_reminder_flow(tmp_path))


async def _test_expiry_reminder_flow(tmp_path) -> None:
    db = DatabaseConnection(tmp_path / "state.db")
    await db.connect()
    storage = SubscriptionStorage(db)
    now = int(time.time())

    # Подписка, которой осталось 23 часа — попадает в напоминание «1 день».
    await storage.create("u1", "7d", 1)
    await storage.activate("u1", "7d", 1, "hash1", "100", "USDT", now + 23 * 3600)
    # Trial на 12 часов — исключается из напоминаний.
    await storage.activate_trial("u2", now + 12 * 3600)
    # Подписка с остатком 2 дня — ещё рано напоминать.
    await storage.create("u3", "7d", 2)
    await storage.activate("u3", "7d", 2, "hash2", "100", "USDT", now + 48 * 3600)

    expiring = await storage.get_expiring_soon()
    assert [s.user_id for s in expiring] == ["u1"]

    # После отметки напоминание не шлётся повторно.
    await storage.mark_expiry_reminder_sent("u1")
    assert await storage.get_expiring_soon() == []

    # При продлении флаг сбрасывается — напоминание снова возможно.
    await storage.create("u1", "7d", 3)
    await storage.activate("u1", "7d", 3, "hash3", "100", "USDT", now + 20 * 3600)
    expiring = await storage.get_expiring_soon()
    assert [s.user_id for s in expiring] == ["u1"]

    # Истёкшая подписка видна только через get_all_expired_active.
    await storage.create("u1", "7d", 4)
    await storage.activate("u1", "7d", 4, "hash4", "100", "USDT", now - 10)
    assert [s.user_id for s in await storage.get_all_expired_active()] == ["u1"]
    assert await storage.get_expiring_soon() == []
    await storage.mark_expired("u1")
    assert await storage.get_all_expired_active() == []

    await db.close()
