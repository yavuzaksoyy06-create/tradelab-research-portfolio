"""Versioned research plans and causal, allowlisted close-based signal rules."""

import hashlib
import hmac
import json
import re
from types import MappingProxyType

import numpy as np
import pandas as pd

from research_workspace.equity_data import SYMBOLS as STRATEGY_SYMBOLS


MAX_STRATEGY_PLAN_BYTES = 4096
STRATEGY_RULES = ("ema_trend", "channel_breakout")
STRATEGY_BOUNDS = MappingProxyType({
    "fast": (2, 199),
    "slow": (3, 200),
    "max_position_bps": (1, 1000),
    "planned_risk_bps": (1, 50),
    "stop_bps": (1, 500),
    "target_bps": (1, 1500),
    "session_loss_bps": (1, 200),
    "max_holding_bars": (1, 4),
})
_PLAN_FLAGS = MappingProxyType({
    "schema": "tradelab.strategy-plan.v1",
    "mode": "OFFLINE_RESEARCH_ONLY",
    "status": "UNVALIDATED",
    "orders_enabled": False,
})
_CONTENT_KEYS = frozenset((*_PLAN_FLAGS, *STRATEGY_BOUNDS, "name", "symbol", "rule"))
_NAME = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9 _.-]{0,62}[A-Za-z0-9])?")
_SHA256 = re.compile(r"[0-9a-f]{64}")


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _digest(content):
    return hashlib.sha256(_canonical(content)).hexdigest()


def _validate_content(content):
    if type(content) is not dict:
        raise ValueError("BOT_STRATEGY_PLAN_SCHEMA")
    content = dict(content)
    if content.keys() != _CONTENT_KEYS:
        raise ValueError("BOT_STRATEGY_PLAN_SCHEMA")
    for key, expected in _PLAN_FLAGS.items():
        if type(content[key]) is not type(expected) or content[key] != expected:
            raise ValueError("BOT_STRATEGY_PLAN_SCOPE")
    if type(content["name"]) is not str or not _NAME.fullmatch(content["name"]):
        raise ValueError("BOT_STRATEGY_PLAN_NAME")
    if type(content["symbol"]) is not str or content["symbol"] not in STRATEGY_SYMBOLS:
        raise ValueError("BOT_STRATEGY_PLAN_SYMBOL")
    if type(content["rule"]) is not str or content["rule"] not in STRATEGY_RULES:
        raise ValueError("BOT_STRATEGY_PLAN_RULE")
    for key, (lower, upper) in STRATEGY_BOUNDS.items():
        value = content[key]
        if type(value) is not int or not lower <= value <= upper:
            raise ValueError("BOT_STRATEGY_PLAN_BOUNDS")
    if content["fast"] >= content["slow"]:
        raise ValueError("BOT_STRATEGY_PLAN_PERIODS")
    return content


def make_strategy_plan(name, symbol, *, rule="ema_trend", fast=9, slow=21,
                       max_position_bps=1000, planned_risk_bps=50, stop_bps=200,
                       target_bps=400, session_loss_bps=200, max_holding_bars=4):
    """Build a content-addressed declaration from fixed rule and risk choices."""
    content = _validate_content({
        **_PLAN_FLAGS,
        "name": name,
        "symbol": symbol,
        "rule": rule,
        "fast": fast,
        "slow": slow,
        "max_position_bps": max_position_bps,
        "planned_risk_bps": planned_risk_bps,
        "stop_bps": stop_bps,
        "target_bps": target_bps,
        "session_loss_bps": session_loss_bps,
        "max_holding_bars": max_holding_bars,
    })
    return {"content": content, "sha256": _digest(content)}


def validate_strategy_plan(envelope):
    """Check the complete schema and digest, then return detached content."""
    if type(envelope) is not dict:
        raise ValueError("BOT_STRATEGY_PLAN_SCHEMA")
    envelope = dict(envelope)
    if envelope.keys() != {"content", "sha256"}:
        raise ValueError("BOT_STRATEGY_PLAN_SCHEMA")
    content = _validate_content(envelope["content"])
    expected = envelope["sha256"]
    actual = _digest(content)
    if (type(expected) is not str or not _SHA256.fullmatch(expected)
            or not hmac.compare_digest(expected, actual)):
        raise ValueError("BOT_STRATEGY_PLAN_DIGEST")
    return content


def encode_strategy_plan(envelope):
    """Encode validated content as deterministic UTF-8 JSON bytes."""
    content = validate_strategy_plan(envelope)
    return _canonical({"content": content, "sha256": _digest(content)})


def _unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("Duplicate JSON key")
        obj[key] = value
    return obj


def _invalid_constant(_):
    raise ValueError("Nonfinite JSON constant")


def decode_strategy_plan(payload):
    """Validate an exact, bounded JSON declaration with unambiguous keys."""
    if type(payload) is not bytes or not 1 <= len(payload) <= MAX_STRATEGY_PLAN_BYTES:
        raise ValueError("BOT_STRATEGY_PLAN_SIZE")
    try:
        envelope = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_object,
                              parse_constant=_invalid_constant)
    except (ValueError, RecursionError):
        raise ValueError("BOT_STRATEGY_PLAN_JSON") from None
    content = validate_strategy_plan(envelope)
    return {"content": content, "sha256": envelope["sha256"]}


def strategy_signals(closes, content):
    """Return positional enter/exit masks from completed closes in caller order."""
    plan = _validate_content(content)
    if not isinstance(closes, (pd.Series, np.ndarray, list, tuple)):
        raise ValueError("BOT_STRATEGY_SIGNAL_INPUT")
    try:
        series = pd.Series(closes, copy=False)
        if series.empty:
            return np.empty(0, dtype=bool), np.empty(0, dtype=bool)
        if not (pd.api.types.is_integer_dtype(series.dtype)
                or pd.api.types.is_float_dtype(series.dtype)):
            raise ValueError
        values = series.to_numpy(dtype=float, na_value=np.nan)
        if not np.isfinite(values).all() or (values <= 0).any():
            raise ValueError
    except (TypeError, ValueError, OverflowError):
        raise ValueError("BOT_STRATEGY_SIGNAL_INPUT") from None

    price = pd.Series(values, copy=False)
    fast, slow = plan["fast"], plan["slow"]
    if plan["rule"] == "ema_trend":
        fast_ema = price.ewm(span=fast, adjust=False, min_periods=fast).mean()
        slow_ema = price.ewm(span=slow, adjust=False, min_periods=slow).mean()
        enter, exit_ = fast_ema > slow_ema, fast_ema <= slow_ema
    else:
        prior = price.shift(1)
        ceiling = prior.rolling(slow).max()
        floor = prior.rolling(fast).min()
        enter, exit_ = price > ceiling, ceiling.notna() & (price < floor)
    return enter.to_numpy(dtype=bool), exit_.to_numpy(dtype=bool)
