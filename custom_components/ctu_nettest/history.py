"""Persistent history of recent measurements backing the average sensors.

The recorder is deliberately not consulted: the integration keeps its own small
ring buffer so the averages survive a restart and stay independent of the
recorder's retention settings.
"""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from statistics import mean
from typing import Any, Self

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN, STORAGE_VERSION
from .rmbt_runner import RmbtResult

_LOGGER = logging.getLogger(__name__)

# Measurements are hours apart, so a short debounce is enough to keep the write
# off the measurement path. A pending save is flushed when Home Assistant stops.
_SAVE_DELAY_SECONDS = 10


@dataclass(frozen=True, slots=True)
class MeasurementSample:
    """One stored measurement, reduced to what the averages need."""

    timestamp: datetime
    download_mbps: float
    upload_mbps: float

    @classmethod
    def from_result(cls, result: RmbtResult) -> Self:
        """Build a sample from a completed measurement."""
        return cls(
            timestamp=result.timestamp,
            download_mbps=result.download_mbps,
            upload_mbps=result.upload_mbps,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Restore a sample from its stored representation."""
        timestamp = dt_util.parse_datetime(data["timestamp"])
        if timestamp is None:
            raise ValueError(f"Unparsable timestamp: {data['timestamp']!r}")
        return cls(
            timestamp=timestamp,
            download_mbps=float(data["download_mbps"]),
            upload_mbps=float(data["upload_mbps"]),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON serialisable representation."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "download_mbps": self.download_mbps,
            "upload_mbps": self.upload_mbps,
        }


class MeasurementHistory:
    """Ring buffer of the newest samples, persisted between restarts."""

    def __init__(self, hass: HomeAssistant, entry_id: str, window_size: int) -> None:
        """Initialize the history for one config entry."""
        self._store: Store[list[dict[str, Any]]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}"
        )
        self._window_size = window_size
        self._samples: deque[MeasurementSample] = deque(maxlen=window_size)

    @property
    def samples(self) -> tuple[MeasurementSample, ...]:
        """Return the retained samples, oldest first."""
        return tuple(self._samples)

    @property
    def sample_count(self) -> int:
        """Return how many samples the averages are based on right now."""
        return len(self._samples)

    @property
    def window_size(self) -> int:
        """Return how many samples are retained at most."""
        return self._window_size

    async def async_load(self) -> None:
        """Load the stored samples, discarding anything unreadable."""
        stored = await self._store.async_load()
        if not isinstance(stored, list):
            return

        restored: list[MeasurementSample] = []
        for item in stored:
            try:
                restored.append(MeasurementSample.from_dict(item))
            except (KeyError, TypeError, ValueError):
                _LOGGER.debug("Discarding unreadable stored sample: %s", item)
        self._samples.extend(restored)

    async def async_flush(self) -> None:
        """Write pending samples out now.

        Home Assistant only flushes a delayed save when it shuts down, so an
        entry reload within the debounce window would otherwise lose the
        newest samples.
        """
        if not self._samples:
            return
        await self._store.async_save(self._data_to_save())

    def add(self, result: RmbtResult) -> None:
        """Append a completed measurement and schedule a save."""
        self._samples.append(MeasurementSample.from_result(result))
        self._schedule_save()

    def resize(self, window_size: int) -> None:
        """Apply a changed window size, keeping the newest samples."""
        if window_size == self._window_size:
            return
        self._window_size = window_size
        self._samples = deque(self._samples, maxlen=window_size)
        self._schedule_save()

    def average_download(self) -> float | None:
        """Return the mean download rate, or None without any sample."""
        return self._average(lambda sample: sample.download_mbps)

    def average_upload(self) -> float | None:
        """Return the mean upload rate, or None without any sample."""
        return self._average(lambda sample: sample.upload_mbps)

    def _average(self, value: Callable[[MeasurementSample], float]) -> float | None:
        if not self._samples:
            return None
        return round(mean(value(sample) for sample in self._samples), 2)

    def _schedule_save(self) -> None:
        self._store.async_delay_save(self._data_to_save, _SAVE_DELAY_SECONDS)

    def _data_to_save(self) -> list[dict[str, Any]]:
        return [sample.to_dict() for sample in self._samples]
