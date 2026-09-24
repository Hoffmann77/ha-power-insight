"""Watch the metering imbalance and raise a repair issue when it persists.

Meters sampled at different moments make the metered sinks briefly read more
than the sources supply; the engine balances that by meeting in the middle and
publishes the gap as ``metering_imbalance``. A brief gap is normal. One that
persists means a misconfigured meter — an inverted sign, or a meter nested
inside another metered circuit — which the user should be told about.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .power_insight import PowerInsight

#: How long the imbalance is averaged over before it counts as persistent.
WINDOW = timedelta(minutes=15)
#: Raise the issue above this share of gross power, clear it below the second —
#: apart, so a borderline installation does not flap.
RAISE_ABOVE = 0.10
CLEAR_BELOW = 0.05


class ImbalanceMonitor:
    """Average the imbalance over a rolling window, as a share of gross power."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, power_insight: PowerInsight,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.power_insight = power_insight
        self.issue_id = f"metering_imbalance_{entry.entry_id}"
        #: ``(time, imbalance W, gross W)``, each held until the next sample.
        self._samples: deque[tuple[datetime, float, float]] = deque()
        self._raised = (
            ir.async_get(hass).async_get_issue(DOMAIN, self.issue_id) is not None
        )

    def update(self, now: datetime | None = None) -> None:
        """Record the current snapshot and re-judge the window."""
        now = now or dt_util.utcnow()
        imbalance = self.power_insight.metering_imbalance
        gross = self.power_insight.gross_power
        if imbalance is None or gross is None:
            # A meter is down: nothing can be judged, so start the window over.
            self._samples.clear()
            return

        self._samples.append((now, imbalance, gross))
        start = now - WINDOW
        # Keep the one sample that was holding when the window opened.
        while len(self._samples) > 1 and self._samples[1][0] <= start:
            self._samples.popleft()
        if self._samples[0][0] > start:
            return  # not a whole window yet

        share = self._share(start, now)
        if share > RAISE_ABOVE and not self._raised:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                self.issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="metering_imbalance",
                translation_placeholders={
                    "entry_title": self.entry.title,
                    "share": f"{share:.0%}",
                },
            )
            self._raised = True
        elif share < CLEAR_BELOW and self._raised:
            ir.async_delete_issue(self.hass, DOMAIN, self.issue_id)
            self._raised = False

    def _share(self, start: datetime, now: datetime) -> float:
        """Return the imbalance over the window as a share of gross power."""
        imbalance_ws = gross_ws = 0.0
        samples = list(self._samples)
        for (time, imbalance, gross), (until, _, _) in zip(
            samples, [*samples[1:], (now, 0.0, 0.0)]
        ):
            held = (until - max(time, start)).total_seconds()
            if held > 0:
                imbalance_ws += imbalance * held
                gross_ws += gross * held
        if gross_ws <= 0:
            return float("inf") if imbalance_ws > 0 else 0.0
        return imbalance_ws / gross_ws
