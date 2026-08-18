import asyncio
import logging
import time
from typing import TYPE_CHECKING

from config import Settings
from mercari.client import MercariClient
from mercari.conditions import parse_search_url
from mercari.devices import DeviceRegistry
from models.item import Item
from storage.urls import UrlStorage, SearchUrlRow
from storage.subscriptions import SubscriptionStorage
from telegram.bot import TelegramNotifier

if TYPE_CHECKING:
    from metrics import MetricsCollector

logger = logging.getLogger(__name__)


class MercariWatcher:
    """Main watch loop: bootstrap, diff via DB, notify."""

    def __init__(
        self,
        settings: Settings,
        url_storage: UrlStorage,
        telegram: TelegramNotifier,
        client: MercariClient,
        devices: DeviceRegistry,
        subs_storage: SubscriptionStorage | None = None,
        admin_user_ids: frozenset[str] = frozenset(),
        metrics: "MetricsCollector | None" = None,
    ) -> None:
        self._settings = settings
        self._url_storage = url_storage
        self._telegram = telegram
        self._client = client
        self._devices = devices
        self._subs_storage = subs_storage
        self._admin_user_ids = admin_user_ids
        self._metrics = metrics
        self._stop = False
        self._force_reload = False
        # Приостановка watcher'а администратором: цикл остаётся жив,
        # но пропускает bootstrap/fetch, пока не будет вызван resume().
        self._paused = False
        self._startup = True
        # No in-memory bootstrap tracking: persisted via seen_items in the DB,
        # so a process restart doesn't re-bootstrap and swallow new listings.
        # Pending-уведомления больше не накапливаем сами: все отправки идут через
        # очередь MessageSender в TelegramNotifier, которая непрерывно
        # дросселирует поток и переотправляет недоставленные в течение того же
        # цикла, а не в начале следующего.
        self._semaphore = asyncio.Semaphore(settings.max_concurrency)

    def stop(self) -> None:
        logger.info("⏹️  Watcher stop() called — setting stop flag")
        self._stop = True

    def force_reload(self) -> None:
        logger.info("🔄 Force reload requested — will skip wait on next cycle")
        self._force_reload = True

    def pause(self) -> None:
        """Приостановить цикл проверки (админ-действие). Не останавливает процесс."""
        if not self._paused:
            logger.info("⏸️  Watcher paused by admin — fetch cycles suspended")
        self._paused = True

    def resume(self) -> None:
        """Возобновить цикл проверки после pause()."""
        if self._paused:
            logger.info("▶️  Watcher resumed by admin — fetch cycles will continue")
        self._paused = False

    @property
    def paused(self) -> bool:
        return self._paused

    _CLEANUP_INTERVAL = 30 * 24 * 3600  # 30 days
    _DEACTIVATED_CLEANUP_AGE = 90 * 24 * 3600  # 90 days

    async def cleanup_loop(self) -> None:
        """Фоновый цикл: раз в 30 дней удаляет старые записи из items и seen_items,
        а также hard-delete URL-ов, деактивированных дольше 90 дней."""
        logger.info("🧹 Cleanup loop started (interval: %s hours)", self._CLEANUP_INTERVAL // 3600)
        while not self._stop:
            await asyncio.sleep(self._CLEANUP_INTERVAL)
            if self._stop:
                break
            try:
                items_del, seen_del = await self._url_storage.cleanup_old_items(
                    self._CLEANUP_INTERVAL
                )
                logger.info(
                    "🧹 Cleanup: deleted %s items and %s seen_items older than %s hours",
                    items_del, seen_del, self._CLEANUP_INTERVAL // 3600,
                )
                urls_del = await self._url_storage.cleanup_deactivated_urls(
                    self._DEACTIVATED_CLEANUP_AGE
                )
                if urls_del > 0:
                    logger.info(
                        "🧹 Cleanup: hard-deleted %s deactivated URL(s) older than %s days",
                        urls_del, self._DEACTIVATED_CLEANUP_AGE // 86400,
                    )
            except Exception as exc:
                logger.error("🧹 Cleanup failed: %s", exc)

    async def run(self) -> None:
        cycle = 0
        logger.info("=" * 50)
        logger.info("👀 WATCHER MAIN LOOP STARTED")
        logger.info("   Check interval: %s seconds", self._settings.check_interval)
        logger.info("   Max concurrency: %s", self._settings.max_concurrency)
        logger.info("=" * 50)

        while not self._stop:
            cycle += 1
            cycle_start = time.monotonic()
            logger.info("─" * 40)
            logger.info("🔄 Watch cycle #%s starting", cycle)

            # Приостановка администратором: цикл жив, но пропускает
            # bootstrap/fetch, пока не будет вызван resume(). Спим короткими
            # интервалами, чтобы быстро отреагировать на resume()/stop().
            if self._paused:
                logger.info("⏸️  Watcher is PAUSED — skipping cycle #%s", cycle)
                if self._metrics is not None:
                    await self._metrics.set_gauge("mercabot_watcher_paused", 1.0)
                await self._wait_while_paused()
                continue

            if self._metrics is not None:
                await self._metrics.set_gauge("mercabot_watcher_paused", 0.0)

            urls = await self._url_storage.get_active_urls()
            logger.info("   Active URLs in DB: %s", len(urls))
            if self._metrics is not None:
                await self._metrics.set_gauge("mercabot_active_urls", float(len(urls)))
                users_set = await self._url_storage.get_all_user_chat_ids()
                await self._metrics.set_gauge("mercabot_active_users", float(len(users_set)))
                if self._subs_storage is not None:
                    subs_total = await self._subs_storage.count_all()
                    await self._metrics.set_gauge("mercabot_active_subscriptions", float(subs_total))
            if not urls:
                logger.info("⏸️  No active URLs — sleeping until next cycle")
                await self._wait_interval()
                continue

            # Bootstrap only URLs that haven't been bootstrapped yet.
            # The flag is persisted in seen_items (any row ⇒ bootstrap done),
            # so a process restart no longer swallows fresh listings.
            new_urls: list[SearchUrlRow] = []
            for url_row in urls:
                bootstrapped = await self._url_storage.is_url_bootstrapped(url_row.id)
                if not bootstrapped:
                    new_urls.append(url_row)
                    logger.info("   📦 URL #%s (%s) needs bootstrap", url_row.id, url_row.name)
                else:
                    logger.debug("   URL #%s (%s) already bootstrapped", url_row.id, url_row.name)

            if new_urls:
                logger.info("   Bootstrap phase: %s URLs to bootstrap", len(new_urls))
                results = await asyncio.gather(
                    *(self._bootstrap_group(rows) for rows in self._group_by_url(new_urls).values()),
                    return_exceptions=True,
                )
                errors = [r for r in results if isinstance(r, Exception)]
                if errors:
                    logger.warning(
                        "   ⚠️  %s URL(s) had errors during bootstrap", len(errors),
                    )
                    if self._metrics is not None:
                        await self._metrics.inc_counter(
                            "mercabot_watch_cycle_errors_total", delta=len(errors),
                        )
                    for i, err in enumerate(errors, 1):
                        logger.warning("      Bootstrap error %s: %s", i, err)
                logger.info("   ✅ Bootstrap phase complete")
            else:
                logger.info("   ✅ All URLs already bootstrapped — skipping bootstrap phase")

            if self._stop:
                logger.info("⏹️  Stop requested after bootstrap — exiting main loop")
                break

            # Pause only after a real bootstrap, so freshly marked items get a
            # buffer before the first diff. Skipping it in steady state avoids
            # a redundant wait that doubled the cycle time (60+60 seconds).
            if new_urls:
                logger.info("   ⏳ Post-bootstrap pause before first diff...")
                await self._wait_interval()

                if self._stop:
                    logger.info("⏹️  Stop requested after bootstrap pause — exiting main loop")
                    break

            # Main watch: fetch each unique URL once, then diff per row.
            # Одинаковый URL у нескольких пользователей запрашивается один раз —
            # diff и уведомления по-прежнему независимы для каждой строки.
            url_groups = self._group_by_url(urls)
            logger.info(
                "   🔄 Fetching %s unique URL(s) in parallel (from %s row(s))...",
                len(url_groups), len(urls),
            )
            results = await asyncio.gather(
                *[self._fetch_and_process_group(rows) for rows in url_groups.values()],
                return_exceptions=True,
            )

            # Log any exceptions from gather
            errors = [r for r in results if isinstance(r, Exception)]
            if errors:
                logger.warning("   ⚠️  %s URL(s) had errors during fetch", len(errors))
                if self._metrics is not None:
                    await self._metrics.inc_counter(
                        "mercabot_watch_cycle_errors_total", delta=len(errors),
                    )
                for i, err in enumerate(errors, 1):
                    logger.warning("      Error %s: %s", i, err)
            else:
                logger.info("   ✅ All URLs fetched successfully")

            if self._stop:
                logger.info("⏹️  Stop requested after fetch — exiting main loop")
                break

            if self._startup:
                self._startup = False
                logger.info("   🔇 Startup cycle complete — notifications enabled for next cycles")
            logger.info("   ✅ Watch cycle #%s complete", cycle)
            cycle_elapsed = time.monotonic() - cycle_start
            if self._metrics is not None:
                await self._metrics.inc_counter("mercabot_watch_cycle_total")
                await self._metrics.observe_histogram(
                    "mercabot_watch_cycle_duration_seconds", cycle_elapsed,
                )
            await self._wait_interval()

        logger.info("=" * 50)
        logger.info("⏹️  WATCHER MAIN LOOP EXITED (total cycles: %s)", cycle)
        logger.info("=" * 50)

    async def _wait_interval(self) -> None:
        logger.info("Waiting %s seconds...", self._settings.check_interval)
        try:
            await asyncio.wait_for(
                self._wait_for_stop(),
                timeout=self._settings.check_interval,
            )
        except asyncio.TimeoutError:
            pass

    async def _wait_for_stop(self) -> None:
        while not self._stop and not self._force_reload:
            await asyncio.sleep(0.5)
        self._force_reload = False

    async def _wait_while_paused(self) -> None:
        """Спит, пока watcher приостановлен админом. Реагирует на resume()/stop()."""
        while self._paused and not self._stop:
            await asyncio.sleep(1.0)

    @staticmethod
    def _group_by_url(url_rows: list[SearchUrlRow]) -> dict[str, list[SearchUrlRow]]:
        """Group URL rows by their literal url string.

        Один и тот же URL, добавленный разными пользователями, возвращает
        одинаковую выдачу Mercari — её можно запросить один раз и раздать
        diff/уведомления по каждой строке независимо.
        """
        groups: dict[str, list[SearchUrlRow]] = {}
        for row in url_rows:
            groups.setdefault(row.url, []).append(row)
        return groups

    async def _bootstrap_group(self, url_rows: list[SearchUrlRow]) -> None:
        """Fetch a URL once and bootstrap each row sharing it (mark seen)."""
        first = url_rows[0]
        logger.info(
            "   📥 [BOOTSTRAP] Fetching URL %s for %s row(s)",
            first.url[:80], len(url_rows),
        )
        async with self._semaphore:
            try:
                condition = parse_search_url(first.url)
                signer = await self._devices.get_signer(first.user_chat_id)
                items = await self._client.search(condition, dpop=signer)
            except Exception as exc:
                logger.error("   ❌ [BOOTSTRAP] Fetch failed for URL %s: %s", first.url[:80], exc)
                raise

        current_ids = {item.id for item in items}
        logger.info(
            "   ✅ [BOOTSTRAP] URL %s returned %s items",
            first.url[:80], len(items),
        )

        for url_row in url_rows:
            # Атомарная фиксация состояния бутстрапа для каждого URL.
            logger.info(
                "   💾 [BOOTSTRAP] Saving %s items to seen_items + items tables (URL #%s)...",
                len(items), url_row.id,
            )
            async with self._url_storage.transaction():
                await self._url_storage.mark_seen_bulk(url_row.id, list(current_ids))
                await self._url_storage.insert_items_bulk(url_row.id, items)
                await self._url_storage.mark_url_bootstrapped(url_row.id)
            logger.info(
                "   ✅ [BOOTSTRAP] URL #%s: %s items marked as seen and stored",
                url_row.id, len(items),
            )

    async def _fetch_and_process_group(self, url_rows: list[SearchUrlRow]) -> None:
        """Fetch a URL once, then diff/notify independently per row."""
        first = url_rows[0]
        logger.info(
            "   📥 Fetching URL %s for %s row(s)",
            first.url[:80], len(url_rows),
        )
        async with self._semaphore:
            try:
                condition = parse_search_url(first.url)
                signer = await self._devices.get_signer(first.user_chat_id)
                items = await self._client.search(condition, dpop=signer)
            except Exception as exc:
                logger.error("   ❌ Fetch failed for URL %s: %s", first.url[:80], exc)
                raise

        current_ids = {item.id for item in items}
        logger.info(
            "   ✅ URL %s returned %s items — checking for new ones",
            first.url[:80], len(items),
        )
        for url_row in url_rows:
            await self._process_new_items(items, current_ids, url_row)

    async def _process_new_items(
        self,
        current_items: list[Item],
        current_ids: set[str],
        url_row: SearchUrlRow,
    ) -> None:
        """Diff against DB seen_items, notify about new ones, record.

        БД-часть (чтение seen → запись items) выполняется
        атомарно внутри transaction(): так параллельные корутины в
        asyncio.gather не наступают на общую транзакцию одного Connection.
        Рассылка в Telegram — ВНЕ транзакции, чтобы не держать соединение
        на время сетевых вызовов.
        """
        # Атомарный diff + запись: между чтением seen_ids и пометкой new_ids
        # другая корутина не сможет вклиниться своим commit'ом.
        async with self._url_storage.transaction():
            seen_ids = await self._url_storage.get_seen_ids(url_row.id)
            new_ids = current_ids - seen_ids

            if not new_ids:
                logger.info("No new items for URL #%s", url_row.id)
                return  # выйдет из transaction() — откатывать нечего, только SELECT

            # Record all current items in items table (for /stats)
            await self._url_storage.insert_items_bulk(url_row.id, current_items)
        # During the first cycle after startup notifications are intentionally
        # suppressed. Those items are safe to mark seen because no delivery is
        # expected for them.
        new_items = [item for item in current_items if item.id in new_ids]
        if self._startup:
            async with self._url_storage.transaction():
                await self._url_storage.mark_seen_bulk(url_row.id, list(new_ids))
            logger.info("   🔇 Startup mode — %s new item(s) marked as seen", len(new_items))
            return

        if self._subs_storage is not None and not await self._subs_storage.is_subscribed(url_row.user_chat_id):
            if url_row.user_chat_id not in self._admin_user_ids and not await self._subs_storage.is_whitelisted(url_row.user_chat_id):
                async with self._url_storage.transaction():
                    await self._url_storage.mark_seen_bulk(url_row.id, list(new_ids))
                logger.info(
                    "   🚫 User %s has no active subscription — %s new item(s) silently skipped",
                    url_row.user_chat_id, len(new_items),
                )
                return

        # Persist each notification before enqueueing it. The sender's success
        # callback marks seen and removes the outbox row only after Telegram
        # accepts the message.
        for item in new_items:
            logger.info("New item detected %s", item.id)
            await self._telegram.send_item(
                url_row.user_chat_id,
                item,
                url_row.name,
                search_url_id=url_row.id,
            )
            logger.info(
                "Queued durable notification for item %s to user %s [%s]",
                item.id, url_row.user_chat_id, url_row.name,
            )
