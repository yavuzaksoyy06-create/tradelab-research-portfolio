"""Streamlit integration smoke tests for the Stage 6 technical analysis bundle."""
from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest


class EquityBundleUITests(unittest.TestCase):
    def test_full_educational_view_renders_structure_and_turkish_evidence(self):
        app = Path(__file__).resolve().parents[1] / "app.py"
        at = AppTest.from_file(str(app), default_timeout=60).run()
        at.radio(key="page").set_value("Equity Research").run()
        self.assertFalse(at.exception)
        self.assertEqual(len(at.get("plotly_chart")), 1)
        self.assertTrue(at.checkbox(key="equity_show_trendlines").value)
        self.assertTrue(at.checkbox(key="equity_show_structure").value)
        self.assertTrue(at.checkbox(key="equity_show_volume_average").value)
        commentary = [element.value for element in at.markdown]
        self.assertTrue(any("Fiyat ve gözlem zamanı" in value
                            for value in commentary))
        self.assertTrue(any("Mekanik trend çizgileri" in value
                            for value in commentary))
        self.assertTrue(any("Veri güvenilirliği ve kapsam" in value
                            for value in commentary))


if __name__ == "__main__":
    unittest.main()
