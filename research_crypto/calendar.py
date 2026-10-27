"""Deterministic, UTC-only 24/7 research calendar for hourly crypto bars (Stage 1).

Design rules (see CRYPTO_RESEARCH_PLAN_030.md, Stage 1):

- Internally every timestamp is timezone-aware UTC (``timezone.utc``).
- Bar opens are hourly on the hour; a bar covers the half-open interval
  ``[bar_open, bar_open + 1h)`` so boundaries never double-count.
- Grid generation covers ``[start, end)`` and excludes every hourly bar whose
  half-open interval ``[bar_open, bar_open + 1h)`` intersects an explicitly
  supplied maintenance window ``[window_start, window_end)``. The overlap
  policy is deliberate: an hourly bar aggregates trades over its whole
  interval, so a bar partially interrupted by downtime (e.g. window
  04:30–05:15 UTC affecting the 04:00 and 05:00 opens) is incomplete and must
  not be expected. Affected bars are excluded, never synthesized or truncated.
- Nothing is ever filled or synthesized: missing bars are reported, never
  invented. Fabricated OHLCV is out of scope forever.
- Timezone-naive timestamps are rejected everywhere with an actionable error;
  aware timestamps in any zone are normalized to UTC before use.
- DST has no effect by construction: internal time is UTC, and a UTC day is
  always exactly 24 hourly bar opens (tests prove this against a DST-change
  Sunday).
- All outputs are ordered tuples; every report is deterministic and repeatable.
- Standard library only — no third-party dependencies in Stage 1.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Sequence, Tuple

__all__ = [
    "UTC",
    "HOUR",
    "BarAlignmentError",
    "CalendarError",
    "CalendarReport",
    "EmptyIntervalError",
    "MaintenanceWindowError",
    "NaiveTimestampError",
    "as_utc",
    "expected_grid",
    "merge_maintenance_windows",
    "validate_bars",
]

UTC = timezone.utc
HOUR = timedelta(hours=1)
_ERROR_EXAMPLES_LIMIT = 10


class CalendarError(ValueError):
    """Base class for every calendar validation failure."""


class NaiveTimestampError(CalendarError):
    """Raised when a timestamp without a timezone offset is supplied."""


class BarAlignmentError(CalendarError):
    """Raised when a grid boundary is not an exact hourly bar-open instant."""


class EmptyIntervalError(CalendarError):
    """Raised when ``[start, end)`` is empty or reversed."""


class MaintenanceWindowError(CalendarError):
    """Raised when a maintenance window is malformed (end <= start, bad type)."""


def as_utc(value, field_name: str = "timestamp") -> datetime:
    """Normalize *value* to an aware UTC ``datetime`` or raise a typed error.

    Accepts ``datetime`` objects (naive ones are rejected) and ISO-8601
    strings such as ``"2026-01-01T00:00:00Z"`` or ``"…+05:30"``. EPOCH dates
    and year-9999 overflow are handled by raising ``CalendarError``.
    """
    if isinstance(value, datetime):
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise NaiveTimestampError(
                f"{field_name} is timezone-naive: {value.isoformat()!r}. "
                "Attach a UTC offset, e.g. '2026-01-01T00:00:00+00:00' or 'Z'."
            )
        return value.astimezone(UTC)
    if isinstance(value, str):
        text = value.strip()
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise CalendarError(
                f"{field_name} is not a valid ISO-8601 timestamp: {value!r}"
            ) from exc
        if parsed.tzinfo is None:
            raise NaiveTimestampError(
                f"{field_name} parses to a timezone-naive datetime: {value!r}. "
                "Attach a UTC offset, e.g. '2026-01-01T00:00:00+00:00' or 'Z'."
            )
        return parsed.astimezone(UTC)
    raise CalendarError(
        f"{field_name} must be datetime or ISO-8601 string, "
        f"got {type(value).__name__}"
    )


def _bar_open(value: datetime, field_name: str) -> datetime:
    stamp = as_utc(value, field_name)
    if stamp.minute or stamp.second or stamp.microsecond:
        raise BarAlignmentError(
            f"{field_name} must be aligned to an exact hourly bar open "
            f"(minutes/seconds must be zero), got {stamp.isoformat()}"
        )
    return stamp


def merge_maintenance_windows(
    maintenance: Sequence[object],
) -> Tuple[Tuple[datetime, datetime], ...]:
    """Validate and merge maintenance windows into disjoint UTC intervals.

    Each entry is a ``(start, end)`` pair (datetime or ISO-8601 string) whose
    half-open interval ``[start, end)`` marks hours with no expected bars.
    Windows may overlap, be adjacent, or lie outside a given grid; empty or
    reversed windows and naive timestamps raise ``MaintenanceWindowError`` /
    ``NaiveTimestampError``. The merge is deterministic: sorted by start time.
    """
    parsed: Tuple[Tuple[datetime, datetime], ...] = ()
    raw = list(maintenance or ())
    for index, window in enumerate(raw):
        label = f"maintenance[{index}]"
        if not isinstance(window, (tuple, list)) or len(window) != 2:
            raise MaintenanceWindowError(
                f"{label} must be a (start, end) pair, got {window!r}"
            )
        window_start = as_utc(window[0], f"{label}.start")
        window_end = as_utc(window[1], f"{label}.end")
        if window_start >= window_end:
            raise MaintenanceWindowError(
                f"{label} interval is empty or reversed: "
                f"start {window_start.isoformat()} >= end {window_end.isoformat()}"
            )
        parsed = parsed + ((window_start, window_end),)
    ordered = sorted(parsed, key=lambda pair: pair[0])
    merged: list = []
    for window_start, window_end in ordered:
        if merged and window_start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], window_end)
        else:
            merged.append([window_start, window_end])
    return tuple((start, end) for start, end in merged)


def expected_grid(start, end, *, maintenance: Sequence[object] = ()) -> Tuple[datetime, ...]:
    """Return the expected hourly bar-open timestamps in ``[start, end)``.

    ``start`` and ``end`` must be exact hourly instants (aware UTC or ISO-8601
    strings). A bar is excluded when its half-open hourly interval
    ``[open, open + 1h)`` intersects any maintenance window ``[ws, we)`` —
    this deliberately excludes bars partially interrupted by downtime, with
    no bar truncation or synthesis. The result is an ordered tuple of aware
    UTC datetimes; adjacent entries differ by exactly one hour (maintenance
    gaps aside). Silently filling gaps is deliberately impossible from this
    function — it never invents bars, it only enumerates expected bar opens.
    """
    grid_start = _bar_open(start, "start")
    grid_end = _bar_open(end, "end")
    if grid_start >= grid_end:
        raise EmptyIntervalError(
            f"grid interval [start, end) is empty: start {grid_start.isoformat()} "
            f">= end {grid_end.isoformat()}"
        )
    windows = merge_maintenance_windows(maintenance)
    grid = []
    cursor = grid_start
    while cursor < grid_end:
        bar_end = cursor + HOUR
        if not any(bar_end > window_start and cursor < window_end
                   for window_start, window_end in windows):
            grid.append(cursor)
        cursor = bar_end
    return tuple(grid)


@dataclass(frozen=True)
class CalendarReport:
    """Strict, typed comparison of observed bar opens against the expected grid.

    ``duplicates`` holds ``(timestamp, count)`` pairs sorted by timestamp.
    ``missing`` and ``off_grid`` hold sorted gridded/non-gridded UTC stamps.
    ``order_ok`` is False when the raw observed sequence is not strictly
    increasing. ``errors`` is a tuple of actionable messages; it is empty
    exactly when ``ok`` is True. No bar is ever filled here.
    """

    expected: Tuple[datetime, ...]
    duplicates: Tuple[Tuple[datetime, int], ...]
    missing: Tuple[datetime, ...]
    off_grid: Tuple[datetime, ...]
    order_ok: bool
    observed_count: int
    errors: Tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def expected_count(self) -> int:
        return len(self.expected)


def _examples(items: Sequence) -> str:
    if len(items) <= _ERROR_EXAMPLES_LIMIT:
        shown = [item.isoformat() for item in items]
        return "; ".join(shown)
    head = "; ".join(item.isoformat() for item in items[:_ERROR_EXAMPLES_LIMIT])
    return f"{head}; … ({len(items) - _ERROR_EXAMPLES_LIMIT} more)"


def validate_bars(
    observed: Iterable,
    start,
    end,
    *,
    maintenance: Sequence[object] = (),
) -> CalendarReport:
    """Strictly compare observed bar opens against the expected 24/7 grid.

    Detection covers: missing expected opens, duplicated opens, opens off the
    hourly grid, and raw-order violations. Malformed input (naive timestamps,
    non-timestamp entries, empty/reversed grids, bad maintenance windows)
    raises before a report is produced — fail closed, never fail open.
    The caller decides what to do with missing bars; this function never
    synthesizes replacement data.
    """
    grid = expected_grid(start, end, maintenance=maintenance)
    observed_stamps: Tuple[datetime, ...] = ()
    for index, value in enumerate(observed):
        observed_stamps += (as_utc(value, f"observed[{index}]"),)
    counts = Counter(observed_stamps)
    duplicates = tuple(
        (stamp, count)
        for stamp, count in sorted(counts.items())
        if count > 1
    )
    unique_observed = set(counts)
    expected_set = set(grid)
    missing = tuple(stamp for stamp in grid if stamp not in unique_observed)
    off_grid = tuple(sorted(stamp for stamp in unique_observed if stamp not in expected_set))
    order_ok = all(
        earlier < later for earlier, later in zip(observed_stamps, observed_stamps[1:])
    )
    errors = []
    if not order_ok:
        first_violation = next(
            (pair for pair in zip(observed_stamps, observed_stamps[1:]) if pair[0] >= pair[1]),
            None,
        )
        errors.append(
            "observed sequence is not strictly increasing: "
            f"{first_violation[0].isoformat()} followed by {first_violation[1].isoformat()}"
        )
    if duplicates:
        shown = ", ".join(f"{stamp.isoformat()}x{count}" for stamp, count in duplicates)
        errors.append(f"duplicated bar opens (timestamp, count): {shown}")
    if off_grid:
        errors.append(f"off-grid bar opens (not hourly UTC opens): {_examples(off_grid)}")
    if missing:
        errors.append(
            f"{len(missing)} missing bar open(s), no gap filling performed: "
            f"{_examples(missing)}"
        )
    return CalendarReport(
        expected=grid,
        duplicates=duplicates,
        missing=missing,
        off_grid=off_grid,
        order_ok=order_ok,
        observed_count=len(observed_stamps),
        errors=tuple(errors),
    )
