"""Versioned provider hours, whole-bar coverage and explicit NY DST handling.

No default real provider: profiles are caller-supplied research assumptions.
All intervals are half-open. A partial closure invalidates the entire bar.
"""
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
import hashlib
import json
import math

UTC = timezone.utc
NY = ZoneInfo('America/New_York')
SYMBOLS = ('EUR/USD', 'USD/JPY', 'GBP/USD')

class CalendarError(ValueError):
    pass

def utc(value):
    try:
        value = datetime.fromisoformat(value.replace('Z', '+00:00')) if isinstance(value, str) else value
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError('timezone required')
        return value.astimezone(UTC)
    except (ValueError, TypeError, AttributeError) as exc:
        raise CalendarError('aware timestamp required') from exc

@dataclass(frozen=True)
class HoursProfile:
    provider: str
    version: str
    assumptions: str
    sunday_open_minute: int = 17 * 60
    friday_close_minute: int = 17 * 60
    rollover_minute: int = 17 * 60
    maintenance_minutes: int = 5
    closures: tuple = ()

    def __post_init__(self):
        for value in (self.provider, self.version, self.assumptions):
            if not isinstance(value, str) or not value.strip():
                raise CalendarError('provider, version and assumptions are required')
        for value in (self.sunday_open_minute, self.friday_close_minute, self.rollover_minute):
            # Deliberately restrict to unambiguous afternoon NY hours, never DST transition hours.
            if type(value) is not int or not 12 * 60 <= value < 23 * 60:
                raise CalendarError('supported NY boundary range: 12:00 through 22:59')
        if type(self.maintenance_minutes) is not int or not 0 <= self.maintenance_minutes <= 60:
            raise CalendarError('maintenance duration must be 0..60 minutes')
        spans = []
        for start, end in self.closures:
            start, end = utc(start), utc(end)
            if end <= start:
                raise CalendarError('closure must have positive duration')
            spans.append((start, end))
        object.__setattr__(self, 'closures', tuple(sorted(spans)))

    @property
    def digest(self):
        data = dict(self.__dict__)
        data['closures'] = [[a.isoformat(), b.isoformat()] for a, b in self.closures]
        return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

def _local_boundary(day, minute):
    return datetime.combine(day, time(minute // 60, minute % 60), NY).astimezone(UTC)

def expected_grid(start, end, *, symbol, profile, minutes=15):
    """UTC opens for fully tradable bars inside [start,end); no filling.

    Maintenance starts Mon-Thu at the profile's NY rollover minute. Holidays
    are NOT inferred: the caller must include known closures in the profile.
    """
    if symbol not in SYMBOLS or not isinstance(profile, HoursProfile):
        raise CalendarError('supported symbol and explicit HoursProfile required')
    if type(minutes) is not int or minutes not in (1, 5, 15, 30, 60):
        raise CalendarError('unsupported interval')
    start, end = utc(start), utc(end)
    step = timedelta(minutes=minutes)
    if end < start or end - start > timedelta(days=366):
        raise CalendarError('range must be ordered and no longer than 366 days')
    if any(t.timestamp() % step.total_seconds() for t in (start, end)):
        raise CalendarError('window boundaries must align with UTC bar grid')
    sessions, closures = [], list(profile.closures)
    day = start.astimezone(NY).date() - timedelta(days=7)
    stop = end.astimezone(NY).date() + timedelta(days=1)
    while day <= stop:
        if day.weekday() == 6:
            sessions.append((_local_boundary(day, profile.sunday_open_minute),
                             _local_boundary(day + timedelta(days=5), profile.friday_close_minute)))
        if day.weekday() in (0, 1, 2, 3) and profile.maintenance_minutes:
            a = _local_boundary(day, profile.rollover_minute)
            closures.append((a, a + timedelta(minutes=profile.maintenance_minutes)))
        day += timedelta(days=1)
    result = []
    cursor = start
    while cursor < end:
        finish = cursor + step
        if (any(a <= cursor and finish <= b for a, b in sessions)
                and not any(cursor < b and finish > a for a, b in closures)):
            result.append(cursor)
        cursor = finish
    return tuple(result)

@dataclass(frozen=True)
class Bar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    available_at: datetime

@dataclass(frozen=True)
class ValidationReport:
    expected_count: int
    observed_count: int
    missing: tuple
    duplicates: tuple
    unexpected: tuple
    invalid: tuple
    ordered: bool

    @property
    def valid(self):
        return not (self.missing or self.duplicates or self.unexpected or self.invalid) and self.ordered

def validate_bars(bars, start, end, *, symbol, profile, as_of, minutes=15):
    """Report defects; never sort, synthesize, drop or repair observations."""
    expected = expected_grid(start, end, symbol=symbol, profile=profile, minutes=minutes)
    bars = tuple(bars)
    cutoff = utc(as_of)
    times, invalid = [], []
    for index, bar in enumerate(bars):
        if not isinstance(bar, Bar):
            invalid.append((index, 'not a Bar')); continue
        try:
            t, available = utc(bar.timestamp), utc(bar.available_at)
            times.append(t)
            values = (bar.open, bar.high, bar.low, bar.close, bar.volume)
            if not all(type(v) in (int, float) and math.isfinite(v) for v in values):
                raise CalendarError('non-finite or non-numeric OHLCV')
            if (min(values[:4]) <= 0 or bar.volume < 0 or
                    bar.low > min(bar.open, bar.close) or bar.high < max(bar.open, bar.close) or bar.low > bar.high):
                raise CalendarError('invalid OHLCV ordering or sign')
            if available < t + timedelta(minutes=minutes) or available > cutoff:
                raise CalendarError('unfinished or unavailable bar')
        except CalendarError as exc:
            invalid.append((index, str(exc)))
    seen, duplicates = set(), set()
    for t in times:
        if t in seen: duplicates.add(t)
        seen.add(t)
    return ValidationReport(len(expected), len(bars), tuple(sorted(set(expected) - seen)),
                            tuple(sorted(duplicates)), tuple(sorted(seen - set(expected))),
                            tuple(invalid), times == sorted(times))
