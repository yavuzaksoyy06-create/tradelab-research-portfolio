"""Security and interaction smoke tests for the public demo entrypoint."""
from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest


DEMO = Path(__file__).resolve().parents[2] / "demo_app.py"


class PublicDemoTests(unittest.TestCase):
    def test_landing_replay_and_research_tabs_render_without_credentials(self):
        app = AppTest.from_file(str(DEMO), default_timeout=90).run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.get("plotly_chart")), 1)
        self.assertEqual(app.selectbox(key="demo_symbol").value, "SPY")
        self.assertGreater(len(app.get("metric")), 3)
        text = "\n".join(str(element.value) for element in app.markdown)
        self.assertIn("TradeLab Research Terminal", text)
        self.assertIn("SYNTHETIC", str(app.warning))

    def test_replay_cursor_works_without_future_in_metrics(self):
        app = AppTest.from_file(str(DEMO), default_timeout=90).run()
        app.slider(key="demo_cursor").set_value(100).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.slider(key="demo_cursor").value, 100)
        metric_values = [str(item.value) for item in app.get("metric")]
        self.assertTrue(any(value.startswith("100 / ") for value in metric_values))

    def test_risk_controls_recalculate_ev(self):
        app = AppTest.from_file(str(DEMO), default_timeout=90).run()
        app.slider(key="ev_probability").set_value(50).run()
        self.assertFalse(app.exception)
        values = [str(item.value) for item in app.get("metric")]
        self.assertIn("+0.500 R", values)

    def test_public_entrypoint_has_no_data_collection_or_order_controls(self):
        content = DEMO.read_text(encoding="utf-8")
        for forbidden in ("ALPACA_API_KEY", "APCA_API_SECRET_KEY", "read_alpaca_history(",
                          "st.file_uploader(", "st.secrets", "submit_order(", "requests.get("):
            self.assertNotIn(forbidden, content)
        self.assertIn("synthetic_fixture", content)


if __name__ == "__main__":
    unittest.main()
