import asyncio
import time

from metrics import MetricsCollector
from storage.connection import DatabaseConnection
from storage.subscriptions import SubscriptionStorage
from storage.urls import UrlStorage
from storage.users import UserStorage
from telegram.handlers import _metric_error_sum, _metric_sum
from telegram.messages import format_admin_stats


def _run(coro):
    return asyncio.run(coro)


def test_subscription_stats(tmp_path) -> None:
    _run(_test_subscription_stats(tmp_path))


async def _test_subscription_stats(tmp_path) -> None:
    db = DatabaseConnection(tmp_path / "state.db")
    await db.connect()
    storage = SubscriptionStorage(db)
    now = int(time.time())

    await storage.create("u1", "7d", 1)
    await storage.activate("u1", "7d", 1, "hash1", "100", "USDT", now + 86400 * 7)
    await storage.create("u2", "30d", 2)
    await storage.activate("u2", "30d", 2, "hash2", "300", "USDT", now + 86400 * 30)
    await storage.create("u3", "7d", 3)
    await storage.activate("u3", "7d", 3, "hash3", "100", "USDT", now + 86400 * 7)
    await storage.activate_trial("u4", now + 43200)
    await storage.whitelist_add("u5", "admin")

    promo = await storage.create_promo(3, "all", "admin")
    assert (await storage.redeem_promo("u1", promo.code)).success is True
    promo2 = await storage.create_promo(3, "all", "admin")
    assert (await storage.redeem_promo("u6", promo2.code)).success is True

    stats = await storage.get_stats()
    assert stats["by_status"] == {"active": 5}
    assert stats["by_plan"] == {"7d": 2, "30d": 1, "trial": 1, "promo": 1}
    assert stats["promo_users"] == 2
    assert stats["revenue"] == {"USDT": 500.0}
    assert stats["whitelist"] == 1

    await storage.mark_expired("u1")
    stats = await storage.get_stats()
    assert stats["by_status"]["expired"] == 1
    assert stats["by_status"]["active"] == 4
    assert stats["promo_users"] == 1

    await db.close()


def test_url_stats(tmp_path) -> None:
    _run(_test_url_stats(tmp_path))


async def _test_url_stats(tmp_path) -> None:
    db = DatabaseConnection(tmp_path / "state.db")
    await db.connect()
    storage = UrlStorage(db)

    await storage.add("https://jp.mercari.com/en/search?keyword=a", "chat-1", "A")
    await storage.add("https://jp.mercari.com/en/search?keyword=b", "chat-2", "B")

    stats = await storage.get_stats()
    assert stats["urls_total"] == 2
    assert stats["urls_active"] == 2
    assert stats["items_total"] == 0
    assert stats["outbox"] == 0

    await storage.add_pending_notification(1, "item-1", "chat-1", "text")
    stats = await storage.get_stats()
    assert stats["outbox"] == 1

    await db.close()


def test_user_count(tmp_path) -> None:
    _run(_test_user_count(tmp_path))


async def _test_user_count(tmp_path) -> None:
    db = DatabaseConnection(tmp_path / "state.db")
    await db.connect()
    storage = UserStorage(db)
    assert await storage.count() == 0
    await storage.set_language("chat-1", "ru")
    await storage.set_language("chat-2", "en")
    assert await storage.count() == 2
    await db.close()


def test_metrics_get_stats() -> None:
    _run(_test_metrics_get_stats())


async def _test_metrics_get_stats() -> None:
    metrics = MetricsCollector()
    await metrics.inc_counter("mercabot_watch_cycle_total", delta=3)
    await metrics.inc_counter("mercabot_mercari_requests_total", labels={"status": "200"})
    await metrics.inc_counter("mercabot_mercari_requests_total", labels={"status": "200"})
    await metrics.inc_counter("mercabot_mercari_requests_total", labels={"status": "timeout"})
    await metrics.observe_histogram("mercabot_watch_cycle_duration_seconds", 2.0)
    await metrics.observe_histogram("mercabot_watch_cycle_duration_seconds", 4.0)

    stats = metrics.get_stats()

    assert stats["mercabot_watch_cycle_total"][""] == 3.0
    assert stats["mercabot_mercari_requests_total"]["status=200"] == 2.0
    assert stats["mercabot_mercari_requests_total"]["status=timeout"] == 1.0
    assert stats["mercabot_watch_cycle_duration_seconds"]["_sum"] == 6.0
    assert stats["mercabot_watch_cycle_duration_seconds"]["_count"] == 2.0


def test_request_error_sum_excludes_success() -> None:
    """Успешные запросы (status=200) не должны попадать в «ошибки»."""
    _run(_test_request_error_sum_excludes_success())


async def _test_request_error_sum_excludes_success() -> None:
    metrics = MetricsCollector()
    await metrics.inc_counter("mercabot_mercari_requests_total", labels={"status": "200"})
    await metrics.inc_counter("mercabot_mercari_requests_total", labels={"status": "200"})
    await metrics.inc_counter("mercabot_mercari_requests_total", labels={"status": "200"})
    await metrics.inc_counter("mercabot_mercari_requests_total", labels={"status": "429"})
    await metrics.inc_counter("mercabot_mercari_requests_total", labels={"status": "timeout"})
    await metrics.inc_counter("mercabot_mercari_requests_total", labels={"status": "network_error"})

    stats = metrics.get_stats()
    total = _metric_sum(stats, "mercabot_mercari_requests_total")
    errors = _metric_error_sum(stats, "mercabot_mercari_requests_total")

    assert total == 6.0
    assert errors == 3.0


def test_admin_stats_message_renders() -> None:
    message = format_admin_stats(
        language="ru",
        uptime="1ч 5м",
        cycles=10,
        cycle_errors=1,
        avg_cycle="12.3",
        requests=100,
        request_errors=2,
        avg_latency="0.45",
        items_found=50,
        sent=40,
        failed=1,
        rate_limited=0,
        queue=3,
        outbox=2,
        users=7,
        urls_active=5,
        urls_total=9,
        subs_active=4,
        subs_pending=1,
        subs_expired=2,
        plans="7d: 3, 30d: 1",
        promo_users=2,
        whitelist=1,
        revenue="USDT: 400.00",
        db_size="0.1",
        items_total=500,
        items_today=12,
        seen_total=480,
    )
    assert "📈" in message
    assert "Циклов: 10" in message
    assert "Промокоды: 2" in message
    assert "Выручка: USDT: 400.00" in message

    message_en = format_admin_stats(
        language="en",
        uptime="1h 5m",
        cycles=10,
        cycle_errors=0,
        avg_cycle="12.3",
        requests=100,
        request_errors=0,
        avg_latency="0.45",
        items_found=50,
        sent=40,
        failed=0,
        rate_limited=0,
        queue=3,
        outbox=2,
        users=7,
        urls_active=5,
        urls_total=9,
        subs_active=4,
        subs_pending=1,
        subs_expired=2,
        plans="7d: 3, 30d: 1",
        promo_users=2,
        whitelist=1,
        revenue="USDT: 400.00",
        db_size="0.1",
        items_total=500,
        items_today=12,
        seen_total=480,
    )
    assert "Cycles: 10" in message_en
