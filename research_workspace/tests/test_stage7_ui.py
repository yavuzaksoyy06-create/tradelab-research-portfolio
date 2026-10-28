"""Visible replay state, preserved chart, and explicitly unvalidated Stage 7 panels."""
from pathlib import Path
import unittest
from streamlit.testing.v1 import AppTest


class Stage7UITests(unittest.TestCase):
    def test_panels_render_and_replay_does_not_show_future_results(self):
        app = Path(__file__).resolve().parents[1] / "app.py"
        at = AppTest.from_file(str(app), default_timeout=60).run()
        at.radio(key="page").set_value("Equity Research").run()
        self.assertFalse(at.exception)
        headings = [e.value for e in at.subheader]
        for title in ("Piyasa Durumu", "Olası Senaryolar", "Tarihsel Kanıt",
                      "Tahmin ve Gerçekleşen Sonuç", "Model Güvenilirliği", "Araştırma Kaydı"):
            self.assertIn(title, headings)
        self.assertEqual(len(at.get("plotly_chart")), 1)
        replay = next(s for s in at.slider if "As-of replay" in s.label)
        replay.set_value(30).run()
        self.assertFalse(at.exception)
        result_tables = [d.value for d in at.dataframe if "Sonuç zamanı" in d.value.columns]
        self.assertEqual(len(result_tables), 1)
        rows = result_tables[0]
        pending = rows.loc[rows["Sonuç zamanı"] == "Henüz görünür değil"]
        self.assertGreater(len(pending), 0)
        self.assertTrue(pending["Gerçekleşen getiri"].isna().all())
        self.assertTrue((rows["Olasılık"] == "Doğrulanmadı").all())
        self.assertTrue(any("INSUFFICIENT OUT-OF-SAMPLE EVIDENCE" in x.value for x in at.warning))
        at.button(key="stage7_evaluate").click().run()
        self.assertFalse(at.exception)
        self.assertTrue(any("INSUFFICIENT" in e.value for e in at.json))
