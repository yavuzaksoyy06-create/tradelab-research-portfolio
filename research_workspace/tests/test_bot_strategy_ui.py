"""Exercise strategy planning through its local Streamlit entry point."""

import json
import unittest
from unittest.mock import patch

import streamlit as st
from streamlit.testing.v1 import AppTest

from research_workspace.bot_strategy import decode_strategy_plan
from research_workspace.bot_strategy_ui import EDIT_KEY, PLAN_KEY


SCRIPT = "from research_workspace.bot_strategy_ui import render\nrender()"
MODULE = "research_workspace.bot_strategy_ui."


class BotStrategyUITests(unittest.TestCase):
    def setUp(self):
        self.original_get_option = st.get_option
        local = patch(MODULE + "st.get_option", side_effect=lambda key:
                      "127.0.0.1" if key == "server.address" else self.original_get_option(key))
        local.start()
        self.addCleanup(local.stop)

    def app(self):
        return AppTest.from_string(SCRIPT, default_timeout=45).run()

    def freeze(self):
        at = self.app()
        at.button(key="bot_plan_freeze").click().run()
        self.assertFalse(at.exception)
        self.assertFalse(at.error)
        return at

    def test_freeze_exports_a_plan_and_edit_revokes_previous_outputs(self):
        with patch(MODULE + "synthetic_fixture") as fixture, patch(MODULE + "run_rehearsal") as rehearse:
            at = self.app()
            self.assertFalse(at.exception)
            self.assertEqual(len(at.get("download_button")), 0)
            self.assertNotIn(PLAN_KEY, at.session_state)
            at.text_input(key="bot_plan_name").set_value("Channel rehearsal")
            at.selectbox(key="bot_plan_symbol").set_value("QQQ")
            at.selectbox(key="bot_plan_rule").set_value("channel_breakout")
            at.number_input(key="bot_plan_planned_risk_bps").set_value(35)
            at.button(key="bot_plan_freeze").click().run()
            self.assertFalse(at.exception)
            envelope = decode_strategy_plan(at.session_state[PLAN_KEY])
            content = envelope["content"]
            self.assertEqual(content["rule"], "channel_breakout")
            self.assertEqual(content["symbol"], "QQQ")
            self.assertEqual(content["planned_risk_bps"], 35)
            self.assertEqual(len(at.text_input), 0)
            self.assertEqual(len(at.get("download_button")), 1)
            self.assertTrue(any(envelope["sha256"] in caption.value for caption in at.caption))
            at.button(key="bot_plan_edit").click().run()
            self.assertFalse(at.exception)
            self.assertNotIn(PLAN_KEY, at.session_state)
            self.assertEqual(at.text_input(key="bot_plan_name").value, "Channel rehearsal")
            self.assertEqual(at.number_input(key="bot_plan_planned_risk_bps").value, 35)
            self.assertEqual(len(at.get("download_button")), 0)
            self.assertNotIn("bot_plan_preview", {button.key for button in at.button})
            fixture.assert_not_called()
            rehearse.assert_not_called()

    def test_invalid_windows_fail_before_preview_or_export(self):
        at = self.app()
        at.number_input(key="bot_plan_fast").set_value(40)
        at.button(key="bot_plan_freeze").click().run()
        self.assertFalse(at.exception)
        self.assertTrue(any("BOT_PLAN_REJECTED" in error.value for error in at.error))
        self.assertNotIn(PLAN_KEY, at.session_state)
        self.assertEqual(len(at.get("download_button")), 0)
        self.assertNotIn("bot_plan_preview", {button.key for button in at.button})

    def test_corrupt_frozen_plan_clears_state_before_exposing_actions(self):
        at = self.freeze()
        at.session_state[PLAN_KEY] = b"SECRET_CORRUPTED_PLAN"
        at.run()
        self.assertFalse(at.exception)
        errors = " ".join(error.value for error in at.error)
        self.assertIn("BOT_PLAN_CACHE_REJECTED", errors)
        self.assertNotIn("SECRET", errors)
        self.assertNotIn(PLAN_KEY, at.session_state)
        self.assertEqual(len(at.get("download_button")), 0)
        self.assertNotIn("bot_plan_preview", {button.key for button in at.button})

    def test_nonlocal_binding_clears_existing_state(self):
        at = self.freeze()
        at.session_state[EDIT_KEY] = at.session_state[PLAN_KEY]
        with patch(MODULE + "st.get_option", side_effect=lambda key:
                   "0.0.0.0" if key == "server.address" else self.original_get_option(key)):
            at.run()
        self.assertFalse(at.exception)
        self.assertNotIn(PLAN_KEY, at.session_state)
        self.assertNotIn(EDIT_KEY, at.session_state)
        self.assertEqual(len(at.button), 0)
        self.assertEqual(len(at.get("download_button")), 0)

    def test_actual_preview_exports_current_synthetic_results_only_on_click(self):
        at = self.freeze()
        self.assertEqual(len(at.metric), 0)
        self.assertEqual(len(at.get("download_button")), 1)
        at.button(key="bot_plan_preview").click().run()
        self.assertFalse(at.exception)
        self.assertFalse(at.error)
        self.assertGreater(int(at.metric[0].value), 0)
        self.assertEqual(len(at.get("download_button")), 3)
        checked = json.loads(at.json[-1].value)
        self.assertIs(checked["synthetic"], True)
        self.assertEqual(checked["real_orders_sent"], 0)
        self.assertEqual(checked["paper_orders_sent"], 0)
        at.run()
        self.assertEqual(len(at.metric), 0)
        self.assertEqual(len(at.get("download_button")), 1)

    def test_preview_failure_is_sanitized_and_keeps_only_plan_export(self):
        with patch(MODULE + "run_rehearsal", side_effect=RuntimeError("SECRET_ENGINE_DETAIL")) as rehearse:
            at = self.freeze()
            rehearse.assert_not_called()
            at.button(key="bot_plan_preview").click().run()
            self.assertFalse(at.exception)
            rehearse.assert_called_once()
            errors = " ".join(error.value for error in at.error)
            self.assertIn("BOT_PLAN_PREVIEW_REJECTED", errors)
            self.assertNotIn("SECRET", errors)
            self.assertEqual(len(at.get("download_button")), 1)
            self.assertEqual(len(at.metric), 0)
