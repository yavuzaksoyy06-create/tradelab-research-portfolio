"""Research plan schema, content binding and causal signal regressions."""

import hashlib
import json
import unittest

import numpy as np
import pandas as pd

from research_workspace import bot_strategy as strategy


class StrategyPlanTests(unittest.TestCase):
    def test_round_trip_binds_the_canonical_content_and_detaches_validation(self):
        plan = strategy.make_strategy_plan("SPY EMA rehearsal", "SPY")
        content = strategy.validate_strategy_plan(plan)
        encoded_content = json.dumps(content, separators=(",", ":"), sort_keys=True).encode()
        self.assertEqual(plan["sha256"], hashlib.sha256(encoded_content).hexdigest())
        self.assertEqual(strategy.decode_strategy_plan(strategy.encode_strategy_plan(plan)), plan)
        self.assertEqual(content["mode"], "OFFLINE_RESEARCH_ONLY")
        self.assertEqual(content["status"], "UNVALIDATED")
        self.assertIs(content["orders_enabled"], False)
        content["fast"] = 3
        self.assertEqual(plan["content"]["fast"], 9)
        self.assertEqual(plan, strategy.make_strategy_plan("SPY EMA rehearsal", "SPY"))

    def test_plan_rejects_tampering_and_refuses_rehashed_scope_escalation(self):
        plan = strategy.make_strategy_plan("SPY EMA rehearsal", "SPY")
        plan["content"]["fast"] = 3
        with self.assertRaisesRegex(ValueError, "BOT_STRATEGY_PLAN_DIGEST"):
            strategy.validate_strategy_plan(plan)
        for name, value in (("mode", "LIVE"), ("status", "VALIDATED"),
                            ("orders_enabled", True), ("orders_enabled", 0),
                            ("broker", "placeholder")):
            with self.subTest(name=name, value=value):
                changed = dict(plan["content"], **{name: value})
                digest = hashlib.sha256(json.dumps(
                    changed, separators=(",", ":"), sort_keys=True).encode()).hexdigest()
                with self.assertRaisesRegex(ValueError, "BOT_STRATEGY_PLAN_(SCOPE|SCHEMA)"):
                    strategy.validate_strategy_plan({"content": changed, "sha256": digest})

    def test_digest_field_has_exact_shape(self):
        plan = strategy.make_strategy_plan("SPY EMA", "SPY")
        for digest in (None, 0, "f" * 63, "F" * 64, "é" * 64):
            with self.subTest(digest=digest):
                with self.assertRaisesRegex(ValueError, "BOT_STRATEGY_PLAN_DIGEST"):
                    strategy.encode_strategy_plan(dict(plan, sha256=digest))
        with self.assertRaisesRegex(ValueError, "BOT_STRATEGY_PLAN_SCHEMA"):
            strategy.validate_strategy_plan(dict(plan, note="unknown"))

    def test_plan_bounds_require_ints_and_disallow_looser_risk(self):
        for key, (lower, upper) in strategy.STRATEGY_BOUNDS.items():
            for value in (True, float(lower), float("inf"), lower - 1, upper + 1):
                with self.subTest(key=key, value=value):
                    with self.assertRaisesRegex(ValueError, "BOT_STRATEGY_PLAN_BOUNDS"):
                        strategy.make_strategy_plan("Strict bounds", "QQQ", **{key: value})
        with self.assertRaisesRegex(ValueError, "BOT_STRATEGY_PLAN_PERIODS"):
            strategy.make_strategy_plan("Bad periods", "QQQ", fast=10, slow=10)
        for kwargs in ({"rule": "custom_script"}, {"rule": ["ema_trend"]}):
            with self.assertRaisesRegex(ValueError, "BOT_STRATEGY_PLAN_RULE"):
                strategy.make_strategy_plan("Bad rule", "QQQ", **kwargs)
        with self.assertRaisesRegex(ValueError, "BOT_STRATEGY_PLAN_SYMBOL"):
            strategy.make_strategy_plan("Unsupported symbol", "BTCUSD")

    def test_display_names_exclude_control_path_and_non_ascii_characters(self):
        for name in ("", " ", "A" * 65, "../path", "A\nB", "Plan / stage", "İşlem", " A"):
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, "BOT_STRATEGY_PLAN_NAME"):
                    strategy.make_strategy_plan(name, "SPY")
        strategy.make_strategy_plan("A" * 64, "SPY")

    def test_decoder_rejects_duplicate_keys_and_invalid_json_before_use(self):
        plan = strategy.make_strategy_plan("SPY EMA", "SPY")
        raw = strategy.encode_strategy_plan(plan)
        for payload in (raw.replace(b'"slow":21', b'"slow":21,"slow":21'),
                        raw.replace(b'"sha256":', b'"sha256":null,"sha256":'),
                        raw.replace(b'"slow":21', b'"slow":NaN'), b'\xff'):
            with self.subTest(length=len(payload)):
                with self.assertRaisesRegex(ValueError, "BOT_STRATEGY_PLAN_JSON"):
                    strategy.decode_strategy_plan(payload)
        with self.assertRaisesRegex(ValueError, "BOT_STRATEGY_PLAN_(JSON|SCHEMA)"):
            strategy.decode_strategy_plan(b"[" * 1200 + b"0" + b"]" * 1200)
        for payload in ("{}", b"", b" " * (strategy.MAX_STRATEGY_PLAN_BYTES + 1)):
            with self.assertRaisesRegex(ValueError, "BOT_STRATEGY_PLAN_SIZE"):
                strategy.decode_strategy_plan(payload)


class StrategySignalTests(unittest.TestCase):
    def test_ema_respects_warmup_and_symmetric_flat_rule(self):
        plan = strategy.make_strategy_plan("EMA 2 3", "SPY", fast=2, slow=3)["content"]
        closes = pd.Series([10., 12., 14., 8., 7., 6., 15.], index=[7, 8, 10, 13, 14, 18, 19])
        enter, exit_ = strategy.strategy_signals(closes, plan)
        np.testing.assert_array_equal(enter, [False, False, True, False, False, False, True])
        np.testing.assert_array_equal(exit_, [False, False, False, True, True, True, False])
        enter, exit_ = strategy.strategy_signals([5., 5., 5.], plan)
        np.testing.assert_array_equal(enter, [False, False, False])
        np.testing.assert_array_equal(exit_, [False, False, True])

    def test_channel_excludes_current_close_and_requires_a_strict_break(self):
        plan = strategy.make_strategy_plan("Channel 2 3", "SPY", rule="channel_breakout",
                                           fast=2, slow=3)["content"]
        enter, exit_ = strategy.strategy_signals([10., 11., 12., 13., 12., 11., 10., 14.], plan)
        np.testing.assert_array_equal(enter, [False, False, False, True, False, False, False, True])
        np.testing.assert_array_equal(exit_, [False, False, False, False, False, True, True, False])

    def test_future_close_perturbation_leaves_each_earlier_decision_unchanged(self):
        prices = np.array([10., 11., 9., 12., 13., 10., 11., 14., 8.])
        for rule in strategy.STRATEGY_RULES:
            with self.subTest(rule=rule):
                plan = strategy.make_strategy_plan("Prefix", "SPY", rule=rule, fast=2, slow=3)["content"]
                original = strategy.strategy_signals(prices, plan)
                for cut in range(1, len(prices)):
                    changed = prices.copy()
                    changed[cut:] *= 10.
                    isolated = strategy.strategy_signals(prices[:cut], plan)
                    perturbed = strategy.strategy_signals(changed, plan)
                    for expected, prefix, changed_rule in zip(original, isolated, perturbed):
                        np.testing.assert_array_equal(prefix, expected[:cut])
                        np.testing.assert_array_equal(changed_rule[:cut], expected[:cut])

    def test_invalid_closes_fail_without_coercion_and_empty_closes_are_neutral(self):
        plan = strategy.make_strategy_plan("Input guards", "SPY")["content"]
        for closes in ([True, False], ["1", "2"], [2., 0.], [np.inf], [np.nan],
                       np.array([[1.]]), [1 + 2j], [2, True], {"first": 10}):
            with self.subTest(closes=closes):
                with self.assertRaisesRegex(ValueError, "BOT_STRATEGY_SIGNAL_INPUT"):
                    strategy.strategy_signals(closes, plan)
        for signals in strategy.strategy_signals([], plan):
            self.assertEqual(signals.dtype, np.dtype(bool))
            self.assertEqual(len(signals), 0)
