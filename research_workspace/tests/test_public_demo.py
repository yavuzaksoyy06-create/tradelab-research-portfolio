"""Smoke tests for the real historical AAPL portfolio demonstration."""
from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest

DEMO = Path(__file__).resolve().parents[2] / "demo_app.py"


class PublicDemoTests(unittest.TestCase):
    def test_real_sample_landing_renders_without_credentials(self):
        at = AppTest.from_file(str(DEMO), default_timeout=90).run()
        self.assertFalse(at.exception)
        self.assertEqual(len(at.get("plotly_chart")), 1)
        self.assertEqual(at.slider(key="demo_cursor").value, 350)
        self.assertGreaterEqual(len(at.get("metric")), 5)
        rendered = "\n".join(str(item.value) for item in at.markdown)
        self.assertIn("TradeLab", rendered)
        self.assertIn("Historical Market Replay", rendered)

    def test_replay_changes_historical_observation_and_not_a_forecast(self):
        at = AppTest.from_file(str(DEMO), default_timeout=90).run()
        first = [str(item.value) for item in at.get("metric")]
        at.slider(key="demo_cursor").set_value(260).run()
        self.assertFalse(at.exception)
        self.assertEqual(at.slider(key="demo_cursor").value, 260)
        after = [str(item.value) for item in at.get("metric")]
        self.assertNotEqual(first[1], after[1])

    def test_risk_controls_recalculate_ev(self):
        at = AppTest.from_file(str(DEMO), default_timeout=90).run()
        at.slider(key="ev_probability").set_value(50).run()
        self.assertFalse(at.exception)
        self.assertIn("+0.500 R", [str(item.value) for item in at.get("metric")])

    def test_public_entrypoint_has_no_secret_or_order_path(self):
        source = DEMO.read_text(encoding="utf-8")
        for forbidden in ("ALPACA_API_KEY", "APCA_API_SECRET_KEY", "read_alpaca_history(",
                          "st.file_uploader(", "st.secrets", "submit_order(", "requests.get(",
                          "synthetic_fixture"):
            self.assertNotIn(forbidden, source)
        self.assertIn("load_daily_sample", source)
        self.assertIn("english_report", source)


if __name__ == "__main__":
    unittest.main()
