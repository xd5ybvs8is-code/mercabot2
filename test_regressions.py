import asyncio
import time

from config import _parse_float, _parse_int
from mercari.conditions import parse_search_url
from metrics import MetricsCollector
from payments import payment_matches
from storage.connection import DatabaseConnection
from storage.subscriptions import SubscriptionStorage
from storage.urls import UrlStorage
from storage.users import UserStorage
from telegram.sender import MessageSender, _OK


def test_bootstrap_marker_survives_seen_cleanup(tmp_path) -> None:
    asyncio.run(_test_bootstrap_marker_survives_seen_cleanup(tmp_path))


async def _test_bootstrap_marker_survives_seen_cleanup(tmp_path) -> None:
    db = DatabaseConnection(tmp_path / "state.db")
    await db.connect()
    urls = UrlStorage(db)
    _, url_id = await urls.add("https://jp.mercari.com/en/search?keyword=x", "user")
    assert await urls.is_url_bootstrapped(url_id) is False
    async with urls.transaction():
        await urls.mark_url_bootstrapped(url_id)
    assert await urls.is_url_bootstrapped(url_id) is True
    await db.conn.execute("DELETE FROM seen_items WHERE search_url_id = ?", (url_id,))
    assert await urls.is_url_bootstrapped(url_id) is True
    await db.close()


def test_subscription_activation_is_idempotent(tmp_path) -> None:
    asyncio.run(_test_subscription_activation_is_idempotent(tmp_path))


async def _test_subscription_activation_is_idempotent(tmp_path) -> None:
    db = DatabaseConnection(tmp_path / "state.db")
    await db.connect()
    storage = SubscriptionStorage(db)
    expires = int(time.time()) + 86400
    await storage.create("user", "7d", 10)
    assert await storage.activate("user", "7d", 10, "hash", "100", "USDT", expires) is True
    assert await storage.activate("user", "7d", 10, "hash", "100", "USDT", expires + 86400) is False
    assert (await storage.get_any("user")).expires_at == expires
    await db.close()


def test_trial_cannot_replace_pending_payment(tmp_path) -> None:
    asyncio.run(_test_trial_cannot_replace_pending_payment(tmp_path))


async def _test_trial_cannot_replace_pending_payment(tmp_path) -> None:
    db = DatabaseConnection(tmp_path / "state.db")
    await db.connect()
    storage = SubscriptionStorage(db)
    await storage.create("user", "7d", 10)
    assert await storage.activate_trial("user", int(time.time()) + 43200) is False
    current = await storage.get_any("user")
    assert current is not None and current.status == "pending" and current.invoice_id == 10
    await db.close()


def test_cancel_pending_is_scoped_to_invoice(tmp_path) -> None:
    asyncio.run(_test_cancel_pending_is_scoped_to_invoice(tmp_path))


async def _test_cancel_pending_is_scoped_to_invoice(tmp_path) -> None:
    db = DatabaseConnection(tmp_path / "state.db")
    await db.connect()
    storage = SubscriptionStorage(db)
    await storage.create("user", "7d", 1)
    await storage.create("user", "30d", 2)
    assert await storage.cancel_pending("user", 1, "cryptobot") is False
    current = await storage.get_any("user")
    assert current is not None and current.status == "pending" and current.invoice_id == 2
    await db.close()


def test_search_url_validation_rejects_host_and_range_errors() -> None:
    for url in (
        "https://jp.mercari.com.evil.example/en/search?keyword=x",
        "https://jp.mercari.com/en/search?price_min=100&price_max=50",
        "https://jp.mercari.com/en/search?price_min=-1",
    ):
        try:
            parse_search_url(url)
        except ValueError:
            continue
        raise AssertionError(f"Invalid URL was accepted: {url}")


def test_metrics_declare_labeled_counter_once() -> None:
    async def build() -> MetricsCollector:
        metrics = MetricsCollector()
        await metrics.inc_counter("requests_total", labels={"status": "200"})
        await metrics.inc_counter("requests_total", labels={"status": "500"})
        return metrics

    metrics = asyncio.run(build())
    rendered = metrics.render_prometheus(metrics.get_snapshot())
    assert rendered.count("# TYPE requests_total counter") == 1


def test_invalid_concurrency_values_are_rejected() -> None:
    try:
        _parse_int("0", 10, "MAX_CONCURRENCY", minimum=1)
    except ValueError:
        pass
    else:
        raise AssertionError("zero concurrency was accepted")

    try:
        _parse_float("nan", 0.3, "REQUEST_DELAY", minimum=0)
    except ValueError:
        pass
    else:
        raise AssertionError("non-finite delay was accepted")


def test_payment_payload_and_amount_are_validated() -> None:
    payload = '{"plan": 7, "user_id": "user"}'
    assert payment_matches(
        "7d", "user", "100", "USDT", payload,
        currency="RUB", expected_asset="USDT",
    )
    assert not payment_matches(
        "7d", "user", "1", "USDT", payload,
        currency="RUB", expected_asset="USDT",
    )


def test_sender_does_not_resend_after_ack_failure() -> None:
    async def run() -> None:
        class FakeClient:
            async def call_api(self, _method, _payload) -> bool:
                return True

        async def failing_ack() -> None:
            raise OSError("database unavailable")

        sender = MessageSender(FakeClient(), rate_per_sec=1, chat_min_interval=0)
        sender.enqueue("chat", "text", show_keyboard=False, on_success=failing_ack)
        result = await sender._send_one(sender._queue.get_nowait())
        assert result == _OK
        assert sender._queue.qsize() == 0

    asyncio.run(run())


def test_platega_cancel_is_best_effort_on_missing_endpoint() -> None:
    asyncio.run(_test_platega_cancel_is_best_effort_on_missing_endpoint())


async def _test_platega_cancel_is_best_effort_on_missing_endpoint() -> None:
    from platega.client import PlategaClient

    class FakeResponse:
        def __init__(self, status: int) -> None:
            self.status = status

        async def json(self) -> dict:
            return {"message": "not found"}

    class FakeContext:
        def __init__(self, status: int) -> None:
            self._status = status

        async def __aenter__(self) -> "FakeResponse":
            return FakeResponse(self._status)

        async def __aexit__(self, *args) -> None:
            return None

    class FakeSession:
        def __init__(self, status: int) -> None:
            self._status = status

        def post(self, *_args, **_kwargs) -> "FakeContext":
            return FakeContext(self._status)

    for status in (404, 405):
        client = PlategaClient("merchant", "secret")
        client._session = FakeSession(status)
        assert await client.cancel_transaction("txn-1") is True


def test_expired_platega_pending_is_cleared_locally(tmp_path) -> None:
    asyncio.run(_test_expired_platega_pending_is_cleared_locally(tmp_path))


async def _test_expired_platega_pending_is_cleared_locally(tmp_path) -> None:
    db = DatabaseConnection(tmp_path / "state.db")
    await db.connect()
    storage = SubscriptionStorage(db)
    await storage.create("user", "7d", 1, payment_gateway="platega", payment_hash="txn-old")
    await db.conn.execute(
        "UPDATE subscriptions SET created_at = ? WHERE user_id = ?",
        (int(time.time()) - 3600, "user"),
    )
    expired = await storage.get_expired_pending(timeout_minutes=30)
    assert len(expired) == 1 and expired[0].payment_hash == "txn-old"
    assert await storage.cancel_pending("user", 1, "platega") is True
    current = await storage.get_any("user")
    assert current is not None and current.status != "pending"
    await db.close()


def test_platega_payment_url_is_persisted(tmp_path) -> None:
    asyncio.run(_test_platega_payment_url_is_persisted(tmp_path))


async def _test_platega_payment_url_is_persisted(tmp_path) -> None:
    db = DatabaseConnection(tmp_path / "state.db")
    await db.connect()
    storage = SubscriptionStorage(db)
    await storage.create(
        "user",
        "7d",
        1,
        payment_gateway="platega",
        payment_hash="txn-1",
        payment_url="https://app.platega.io/pay/txn-1",
    )
    current = await storage.get_any("user")
    assert current is not None and current.payment_url == "https://app.platega.io/pay/txn-1"
    await db.close()


def test_sbp_keyboard_omits_empty_payment_url() -> None:
    from telegram.keyboard import build_sbp_invoice_keyboard

    markup = build_sbp_invoice_keyboard("", "txn-1")
    assert len(markup["inline_keyboard"]) == 2
    assert all("url" not in button for row in markup["inline_keyboard"] for button in row)


def test_bot_offset_state_persists(tmp_path) -> None:
    async def run() -> None:
        db = DatabaseConnection(tmp_path / "state.db")
        await db.connect()
        users = UserStorage(db)
        await users.set_state("telegram_update_offset", "42")
        assert await users.get_state("telegram_update_offset") == "42"
        await db.close()

    asyncio.run(run())
