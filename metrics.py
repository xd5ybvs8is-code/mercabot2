import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

import aiohttp
from aiohttp import web

logger = logging.getLogger(__name__)

_HISTOGRAM_BUCKETS = (
    0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0,
)


@dataclass
class _Histogram:
    buckets: dict[float, int] = field(default_factory=dict)
    sum: float = 0.0
    count: int = 0

    def __post_init__(self) -> None:
        if not self.buckets:
            for b in _HISTOGRAM_BUCKETS:
                self.buckets[b] = 0
            self.buckets[float("+Inf")] = 0


class MetricsCollector:
    """Thread-safe (asyncio) collector for counters, gauges, and histograms.

    Renders to Prometheus text format with no external dependencies.
    """

    def __init__(self) -> None:
        self._counters: dict[str, int] = {}
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, _Histogram] = {}
        self._labels: dict[str, dict[str, str]] = {}
        self._lock = asyncio.Lock()

    async def inc_counter(self, name: str, labels: dict[str, str] | None = None, delta: int = 1) -> None:
        key = self._metric_key(name, labels)
        async with self._lock:
            self._counters[key] = self._counters.get(key, 0) + delta
            if labels:
                self._labels[key] = labels

    async def set_gauge(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        key = self._metric_key(name, labels)
        async with self._lock:
            self._gauges[key] = value
            if labels:
                self._labels[key] = labels

    async def observe_histogram(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        key = self._metric_key(name, labels)
        async with self._lock:
            if labels:
                self._labels[key] = labels
            if key not in self._histograms:
                self._histograms[key] = _Histogram()
            h = self._histograms[key]
            h.sum += value
            h.count += 1
            for bound in _HISTOGRAM_BUCKETS:
                if value <= bound:
                    h.buckets[bound] += 1
            h.buckets[float("+Inf")] += 1

    async def snapshot(self) -> dict[str, tuple[str, float]]:
        async with self._lock:
            return {
                k: (self._key_name(k), float(v))
                for k, v in {**self._counters, **self._gauges}.items()
            }

    def render_prometheus(self, snapshot: dict[str, tuple[str, float]]) -> str:
        lines: list[str] = []
        for key, (name, value) in snapshot.items():
            labels = self._labels.get(key)
            label_str = self._format_labels(labels)
            if key in self._counters:
                lines.append(f"# TYPE {name} counter")
                lines.append(f"{name}{label_str} {int(value)}")
            elif key in self._histograms:
                lines.append(f"# TYPE {name} histogram")
                h = self._histograms[key]
                lines.append(f"{name}_sum{label_str} {h.sum}")
                lines.append(f"{name}_count{label_str} {h.count}")
                for bound in _HISTOGRAM_BUCKETS + (float("+Inf"),):
                    lines.append(
                        f"{name}_bucket{label_str}{{le=\"{bound}\"}} {h.buckets.get(bound, 0)}"
                    )
            else:
                lines.append(f"# TYPE {name} gauge")
                lines.append(f"{name}{label_str} {value}")
        lines.append("")
        return "\n".join(lines)

    def get_snapshot(self) -> dict[str, tuple[str, float]]:
        result: dict[str, tuple[str, float]] = {}
        for k, v in self._counters.items():
            result[k] = (self._key_name(k), float(v))
        for k, v in self._gauges.items():
            result[k] = (self._key_name(k), float(v))
        for k, h in self._histograms.items():
            result[k] = (self._key_name(k), float(h.sum))
        return result

    def get_stats(self) -> dict[str, dict[str, float]]:
        """Структурированная статистика для админ-панели.

        Возвращает {metric_name: {label: value}} — лейблы собраны в
        словарь (включая пустой ""), чтобы /admin_stats мог агрегировать
        значения по статусам и считать средние по гистограммам.
        """
        result: dict[str, dict[str, float]] = {}
        for key, value in self._counters.items():
            result.setdefault(self._key_name(key), {})[self._label_value(key)] = float(value)
        for key, value in self._gauges.items():
            result.setdefault(self._key_name(key), {})[self._label_value(key)] = float(value)
        for key, hist in self._histograms.items():
            name = self._key_name(key)
            result.setdefault(name, {})
            result[name]["_sum"] = hist.sum
            result[name]["_count"] = float(hist.count)
        return result

    @staticmethod
    def _label_value(key: str) -> str:
        parts = key.split(",")
        if len(parts) == 1:
            return ""
        return ",".join(parts[1:])

    @staticmethod
    def _metric_key(name: str, labels: dict[str, str] | None) -> str:
        if not labels:
            return name
        parts = [name]
        for k in sorted(labels):
            parts.append(f"{k}={labels[k]}")
        return ",".join(parts)

    @staticmethod
    def _key_name(key: str) -> str:
        return key.split(",")[0]

    @staticmethod
    def _format_labels(labels: dict[str, str] | None) -> str:
        if not labels:
            return ""
        items = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        return "{" + items + "}"


class MetricsServer:
    """A thin aiohttp HTTP server exposing /health and /metrics.

    Integrates with the running watcher, sender, and database for live
    status queries.
    """

    def __init__(
        self,
        metrics: MetricsCollector,
        host: str = "127.0.0.1",
        port: int = 9090,
        *,
        watcher=None,
        sender=None,
        db=None,
        db_path: Path | None = None,
    ) -> None:
        self._metrics = metrics
        self._host = host
        self._port = port
        self._watcher = watcher
        self._sender = sender
        self._db = db
        self._db_path = db_path
        self._runner: web.AppRunner | None = None
        self._started_at = time.time()

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/health", self._health_handler)
        app.router.add_get("/metrics", self._metrics_handler)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self._host, self._port)
        await site.start()
        logger.info(
            "📊 Metrics server listening on http://%s:%s",
            self._host, self._port,
        )

    async def stop(self) -> None:
        if self._runner is not None:
            logger.info("📊 Stopping metrics server...")
            await self._runner.cleanup()
            self._runner = None
            logger.info("📊 Metrics server stopped")

    async def _health_handler(self, request: web.Request) -> web.Response:
        status_code = 200
        health: dict[str, object] = {
            "status": "ok",
            "uptime_seconds": round(time.time() - self._started_at, 1),
        }

        if self._sender is not None:
            stats_fn = getattr(self._sender, "sender_stats", None) or getattr(self._sender, "stats", None)
            if stats_fn is not None:
                sender_stats = stats_fn()
                queue_size = sender_stats.get("queue_size", 0)
                health["sender_queue_size"] = queue_size
                health["sender_rate"] = f"{sender_stats.get('current_rate', 0)}/{sender_stats.get('target_rate', 0)} msg/s"
                if isinstance(queue_size, int) and queue_size > 500:
                    status_code = 503
                    health["status"] = "degraded"
                    health["warning"] = f"sender queue overloaded ({queue_size} pending)"

        if self._watcher is not None:
            health["watcher_paused"] = getattr(self._watcher, "paused", False)

        if self._db_path is not None:
            try:
                db_size = self._db_path.stat().st_size
                health["db_size_bytes"] = db_size
            except OSError:
                health["db_size_bytes"] = "unavailable"

        return web.json_response(health, status=status_code)

    async def _metrics_handler(self, request: web.Request) -> web.Response:
        snapshot = self._metrics.get_snapshot()

        if self._sender is not None:
            stats_fn = getattr(self._sender, "sender_stats", None) or getattr(self._sender, "stats", None)
            if stats_fn is not None:
                stats = stats_fn()
                snapshot["mercabot_sender_queue_size gauge"] = ("mercabot_sender_queue_size", float(stats.get("queue_size", 0)))

        if self._watcher is not None:
            snapshot["mercabot_watcher_paused gauge"] = ("mercabot_watcher_paused", 1.0 if getattr(self._watcher, "paused", False) else 0.0)

        return web.Response(text=self._metrics.render_prometheus(snapshot), content_type="text/plain; version=0.0.4")
