"""Streamlit integration smoke tests for the Stage 6 technical analysis bundle."""
from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from research_workspace import equity_ui
from research_workspace.equity_data import synthetic_fixture


class AlpacaSnapshotAccessorTests(unittest.TestCase):
    """Source-bound handoff uses simulated bars labelled as API fixtures."""

    def pack(self):
        frame, metadata = synthetic_fixture('SPY')
        metadata = {**metadata, 'synthetic': False, 'feed': 'iex',
                    'provider_api_response': True, 'currency': 'USD',
                    'provenance_notes': {'fixture': ['offline']}}
        identity = ('SPY', 'iex', '2026-10-05', '2026-10-16')
        digest = equity_ui._provider_snapshot_digest(identity, frame, metadata)
        return identity, frame, metadata, digest

    def test_malformed_or_mutated_cache_clears_before_returning_source(self):
        identity, frame, metadata, digest = self.pack()
        changed = frame.copy()
        changed.loc[0, 'close'] += .01
        for saved in ((), ('bad',), {'bad': 1},
                      (identity, changed, metadata, digest),
                      (identity, frame, {**metadata, 'feed': 'sip'}, digest)):
            with self.subTest(kind=type(saved).__name__):
                state = {'equity_provider_snapshot': saved}
                with patch.object(equity_ui.st, 'session_state', state), \
                     patch.object(equity_ui.st, 'get_option', return_value='127.0.0.1'):
                    self.assertIsNone(equity_ui.get_loaded_alpaca_snapshot())
                self.assertNotIn('equity_provider_snapshot', state)

    def test_returned_bars_and_nested_metadata_are_detached(self):
        saved = self.pack()
        state = {'equity_provider_snapshot': saved}
        with patch.object(equity_ui.st, 'session_state', state), \
             patch.object(equity_ui.st, 'get_option', return_value='127.0.0.1'):
            frame, metadata = equity_ui.get_loaded_alpaca_snapshot('SPY')
            original_close = frame.close.iloc[0]
            frame.loc[0, 'close'] = 9999
            metadata['provenance_notes']['fixture'].append('changed')
            again, source = equity_ui.get_loaded_alpaca_snapshot('SPY')
        self.assertEqual(again.close.iloc[0], original_close)
        self.assertEqual(source['provenance_notes'], {'fixture': ['offline']})

    def test_other_symbol_cannot_consume_or_relabel_cached_source(self):
        state = {'equity_provider_snapshot': self.pack()}
        with patch.object(equity_ui.st, 'session_state', state), \
             patch.object(equity_ui.st, 'get_option', return_value='127.0.0.1'):
            self.assertIsNone(equity_ui.get_loaded_alpaca_snapshot('QQQ'))
            self.assertIn('equity_provider_snapshot', state)
            _, metadata = equity_ui.get_loaded_alpaca_snapshot('SPY')
            self.assertEqual(metadata['symbol'], 'SPY')


class EquityBundleUITests(unittest.TestCase):
    def test_full_educational_view_renders_structure_and_turkish_evidence(self):
        app = Path(__file__).resolve().parents[1] / "app.py"
        at = AppTest.from_file(str(app), default_timeout=60).run()
        at.radio(key="page").set_value("Equity Research").run()
        at.radio(key="equity_mode").set_value("Synthetic teaching example").run()
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
