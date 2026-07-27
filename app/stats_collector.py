"""Real-time system and application statistics for the dashboard."""

from __future__ import annotations

import logging
import time
import psutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional, Tuple

from app import __version__

logger = logging.getLogger(__name__)

# Render's free web service caps a process at 512MB.
DEFAULT_MEMORY_LIMIT_MB = 512.0
CACHE_TTL_SECONDS = 5.0


@dataclass
class SystemStats:
    memory_used_mb: float = 0.0
    memory_percent: float = 0.0
    cpu_percent: float = 0.0
    bot_status: str = "offline"
    uptime_seconds: int = 0
    uptime_formatted: str = "0m"
    last_message_time: Optional[str] = None
    codes_sent: int = 0
    codes_failed: int = 0
    version: str = __version__
    last_update: str = field(default_factory=lambda: _iso_now())

    def to_dict(self) -> dict:
        return asdict(self)


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _memory_limit_mb() -> float:
    """Best-effort container memory limit, falling back to the Render free tier."""
    for path in (
        "/sys/fs/cgroup/memory.max",  # cgroup v2
        "/sys/fs/cgroup/memory/memory.limit_in_bytes",  # cgroup v1
    ):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                raw = handle.read().strip()
            if raw and raw != "max":
                limit = int(raw) / (1024 * 1024)
                # Unbounded cgroups report an absurdly large number.
                if 0 < limit < 1024 * 64:
                    return limit
        except (OSError, ValueError):
            continue
    return DEFAULT_MEMORY_LIMIT_MB


class StatsCollector:
    """Samples metrics at most once every :data:`CACHE_TTL_SECONDS`."""

    def __init__(self, telegram_client=None, discord_sender=None) -> None:
        self.telegram_client = telegram_client
        self.discord_sender = discord_sender

        self._memory_limit_mb = _memory_limit_mb()
        self._started_at = time.monotonic()
        self._cache: Optional[SystemStats] = None
        self._cached_at = 0.0
        self._process = psutil.Process()
        # Prime the CPU usage baseline
        self._process.cpu_percent()

    # -- individual metrics -------------------------------------------------

    def get_memory_usage(self) -> Tuple[float, float]:
        """(resident MB, percent of the container limit)."""
        try:
            mem = self._process.memory_info()
            used_mb = mem.rss / (1024 * 1024)
            percent = (used_mb / self._memory_limit_mb) * 100.0
            return used_mb, min(100.0, percent)
        except (psutil.Error, OSError):
            return 0.0, 0.0

    def get_cpu_usage(self) -> float:
        # Non-blocking: measured against the previous call, so no sleep cost.
        try:
            # CPU percent can exceed 100% on multicore systems.
            count = psutil.cpu_count(logical=True)
            if not count:
                count = 1
            return self._process.cpu_percent(interval=None) / count
        except (psutil.Error, OSError, TypeError):
            return 0.0

    def calculate_uptime(self) -> int:
        return int(time.monotonic() - self._started_at)

    def get_uptime_formatted(self) -> str:
        return format_duration(self.calculate_uptime())

    # -- aggregate ----------------------------------------------------------

    def collect(self, force: bool = False) -> SystemStats:
        """Return the current stats, reusing a cached sample for 5 seconds."""
        now = time.monotonic()
        if not force and self._cache is not None and (now - self._cached_at) < CACHE_TTL_SECONDS:
            return self._cache

        stats = SystemStats()
        try:
            stats.memory_used_mb, stats.memory_percent = self.get_memory_usage()
            stats.cpu_percent = self.get_cpu_usage()
        except Exception as exc:
            logger.warning("Stats: could not sample process metrics")

        stats.uptime_seconds = self.calculate_uptime()
        stats.uptime_formatted = format_duration(stats.uptime_seconds)

        if self.telegram_client is not None:
            stats.bot_status = self.telegram_client.status
            last_message = self.telegram_client.last_message_time
            if last_message:
                stats.last_message_time = last_message.replace(microsecond=0).isoformat().replace(
                    "+00:00", "Z"
                )

        if self.discord_sender is not None:
            stats.codes_sent = self.discord_sender.sent_count
            stats.codes_failed = self.discord_sender.failed_count

        stats.last_update = _iso_now()
        self._cache = stats
        self._cached_at = now
        return stats


def format_duration(seconds: int) -> str:
    """Format a duration as "1d 2h 30m" (minutes-resolution, "42s" if shorter)."""
    seconds = max(0, int(seconds))
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, secs = divmod(rest, 60)

    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if not parts:
        parts.append(f"{secs}s")
    return " ".join(parts)
