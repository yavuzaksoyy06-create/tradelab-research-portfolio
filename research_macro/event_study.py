"""Offline, synthetic-only descriptive event returns. No signal or execution API.

A price return is available only for a fully covered requested window. Closed
sessions and missing observations are distinct, and neither is interpolated.
Review-time document verification is not a claim that a trade could have used
the archived document at historical release time.
"""
from dataclasses import dataclass, asdict
from datetime import timedelta
import hashlib
import json
import math
from research_fx.calendar import utc, expected_grid, SYMBOLS
from .events import require_integrity_verified
from .availability import response_label_available

class StudyError(ValueError):
    pass

@dataclass(frozen=True)
class Instrument:
    symbol: str
    asset_class: str
    quote_currency: str
    price_basis: str

    def __post_init__(self):
        if self.asset_class not in ('fx', 'equity', 'crypto'):
            raise StudyError('unsupported asset class')
        if any(not isinstance(v, str) or not v.strip() for v in asdict(self).values()):
            raise StudyError('explicit instrument metadata required')
        if self.asset_class == 'fx' and self.symbol not in SYMBOLS:
            raise StudyError('unsupported FX symbol')

@dataclass(frozen=True)
class SessionGrid:
    """Explicit synthetic session schedule, bound to symbol and exact window.

    Future production adapters must review provider schedules independently;
    a self-declared digest does not establish that an exchange was open.
    """
    symbol: str
    start: object
    end: object
    minutes: int
    opens: tuple
    calendar_reference: str
    calendar_sha256: str

    def __post_init__(self):
        start, end = utc(self.start), utc(self.end)
        if type(self.minutes) is not int or self.minutes not in (1, 5, 15, 30, 60):
            raise StudyError('unsupported interval')
        seconds = self.minutes * 60
        if not start < end or end-start > timedelta(days=7):
            raise StudyError('event window must be positive and at most seven days')
        if start.timestamp() % seconds or end.timestamp() % seconds:
            raise StudyError('unaligned window')
        opens = tuple(utc(t) for t in self.opens)
        if opens != tuple(sorted(set(opens))):
            raise StudyError('session grid must be ordered and unique')
        if any(t < start or t+timedelta(minutes=self.minutes) > end or t.timestamp() % seconds for t in opens):
            raise StudyError('session open outside aligned window')
        if (not self.symbol or not self.calendar_reference or len(self.calendar_sha256) != 64
                or any(c not in '0123456789abcdef' for c in self.calendar_sha256)):
            raise StudyError('calendar reference and SHA256 required')
        object.__setattr__(self, 'start', start)
        object.__setattr__(self, 'end', end)
        object.__setattr__(self, 'opens', opens)

def fx_session_grid(start, end, *, symbol, profile, minutes=15):
    return SessionGrid(symbol, start, end, minutes,
                       expected_grid(start, end, symbol=symbol, profile=profile, minutes=minutes),
                       profile.provider + ':' + profile.version, profile.digest)

@dataclass(frozen=True)
class Observation:
    timestamp: object
    open: float
    close: float
    available_at: object

@dataclass(frozen=True)
class StudyResult:
    status: str
    raw_return: float | None
    pre_release_return: float | None
    post_release_return: float | None
    expected_count: int
    observed_count: int
    missing: tuple
    closed_bar_count: int
    provenance: dict
    limitations: tuple

LIMITATIONS = (
    'Synthetic descriptive price returns only; not alpha, a forecast or causal evidence.',
    'No costs, spreads, slippage, carry, funding, dividends or statistical significance estimated.',
    'Calendar and market-price provenance are declared synthetic inputs, not vendor authentication.',
    'Pre/post split requires the actual release to coincide exactly with a bar boundary inside the window.',
    'Document review may be retrospective; historical observability relies on declared availability metadata.',
)

def study_event(event, observations, *, instrument, grid, as_of, source_reference,
                synthetic, verification_inputs):
    """Simple raw window return = last close / first open - 1 (fraction).

    Gate the whole label before evaluating any return. For a straddling
    window, additionally expose independent pre/post returns on either side
    of the actual release, without assuming inter-bar price continuity.
    """
    if synthetic is not True:
        raise StudyError('this initial core accepts explicitly synthetic research only')
    if not isinstance(instrument, Instrument) or not isinstance(grid, SessionGrid):
        raise StudyError('validated instrument and session grid required')
    if not isinstance(source_reference, str) or not source_reference.strip():
        raise StudyError('price source reference required')
    evidence = require_integrity_verified(event, **verification_inputs)
    if event.research_mode != 'explanatory_event_study' or event.document.role != 'announcement':
        raise StudyError('an explanatory event with an announcement document is required')
    if (instrument.symbol != grid.symbol or utc(event.response_window_start) != grid.start
            or utc(event.response_window_end) != grid.end):
        raise StudyError('event, instrument and calendar window must match exactly')
    cutoff = utc(as_of)
    observations = tuple(observations)
    step = timedelta(minutes=grid.minutes)
    times, availability, serialized = [], [], []
    for row in observations:
        if not isinstance(row, Observation):
            raise StudyError('Observation required')
        t, available = utc(row.timestamp), utc(row.available_at)
        if available < t + step:
            raise StudyError('observation availability precedes completed bar')
        if not all(type(v) in (int, float) and math.isfinite(v) and v > 0 for v in (row.open, row.close)):
            raise StudyError('prices must be finite and positive')
        times.append(t); availability.append(available)
        serialized.append([t.isoformat(), row.open, row.close, available.isoformat()])
    if times != sorted(set(times)):
        raise StudyError('duplicate or unsorted observations')
    if set(times) - set(grid.opens):
        raise StudyError('unexpected observations outside provider session grid')
    missing = tuple(t.isoformat() for t in grid.opens if t not in set(times))
    closed_count = int((grid.end-grid.start) / step) - len(grid.opens)
    provenance = {'event_digest': event.record_digest, 'verification': asdict(evidence),
                  'instrument': asdict(instrument), 'source_reference': source_reference,
                  'synthetic': True, 'as_of': cutoff.isoformat(),
                  'window_start': grid.start.isoformat(), 'window_end': grid.end.isoformat(),
                  'bar_minutes': grid.minutes, 'calendar_reference': grid.calendar_reference,
                  'calendar_sha256': grid.calendar_sha256,
                  'grid_sha256': hashlib.sha256(json.dumps([t.isoformat() for t in grid.opens], separators=(',', ':')).encode()).hexdigest(),
                  'observations_sha256': hashlib.sha256(json.dumps(serialized, separators=(',', ':'), allow_nan=False).encode()).hexdigest()}
    def result(status, raw=None, pre=None, post=None):
        return StudyResult(status, raw, pre, post, len(grid.opens), len(observations), missing, closed_count, provenance, LIMITATIONS)
    if not response_label_available(event, cutoff, observations_available_at=availability):
        return result('not_yet_available')
    if missing:
        return result('missing_observations')
    if closed_count:
        return result('session_closure')
    if not observations:
        return result('no_observations')
    def raw_return(rows):
        value = rows[-1].close / rows[0].open - 1
        if not math.isfinite(value):
            raise StudyError('return overflow')
        return value
    raw = raw_return(observations)
    release = utc(event.actual_release_ts)
    pre = post = None
    if release in times and grid.start < release < grid.end:
        split = times.index(release)
        pre, post = raw_return(observations[:split]), raw_return(observations[split:])
    return result('available', raw, pre, post)
