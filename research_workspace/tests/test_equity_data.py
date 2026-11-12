"""Stage 6 equity data checks: offline, no feeds and no order endpoints."""
from datetime import date, datetime, timezone
import unittest
from unittest.mock import patch
import json

import pandas as pd
import streamlit as st

from research_workspace.equity_provenance import replay_manifest, manifest_json
from research_workspace.equity_provider import EquityProviderError
from research_workspace.equity_data import (
    REQUIRED, MAX_BYTES, analyze_prefix, read_uploaded_csv, synthetic_fixture
)


class EquityDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame, cls.meta = synthetic_fixture('SPY')
        cls.raw = cls.frame[list(REQUIRED)].to_csv(index=False).encode('utf-8')

    def test_synthetic_is_explicitly_not_real_market_data(self):
        self.assertTrue(self.meta['synthetic'])
        self.assertIn('SYNTHETIC', self.meta['origin'])
        self.assertFalse(self.meta['feed_verified'])
        self.assertFalse(self.meta['orders_enabled'])
        self.assertGreater(len(self.frame), 100)

    def test_uploaded_complete_sessions_are_structurally_validated(self):
        frame, meta = read_uploaded_csv(self.raw, 'SPY')
        self.assertEqual(len(frame), len(self.frame))
        self.assertFalse(meta['synthetic'])
        self.assertFalse(meta['feed_verified'])
        self.assertFalse(meta['point_in_time_archive_verified'])
        self.assertEqual(len(meta['input_sha256']), 64)

    def test_missing_bar_rejected_instead_of_filled(self):
        frame = self.frame[list(REQUIRED)].drop(index=[10])
        with self.assertRaises(ValueError):
            read_uploaded_csv(frame.to_csv(index=False).encode(), 'SPY')

    def test_duplicate_bar_rejected(self):
        df = self.frame[list(REQUIRED)]
        duplicated = pd.concat([df.iloc[:5], df.iloc[[4]], df.iloc[5:]], ignore_index=True)
        with self.assertRaises(ValueError):
            read_uploaded_csv(duplicated.to_csv(index=False).encode(), 'SPY')

    def test_unordered_bar_rejected(self):
        df = self.frame[list(REQUIRED)].copy()
        df.iloc[[5,6]] = df.iloc[[6,5]].to_numpy()
        with self.assertRaises(ValueError):
            read_uploaded_csv(df.to_csv(index=False).encode(), 'SPY')

    def test_naive_timestamps_rejected(self):
        df = self.frame[list(REQUIRED)].copy()
        df['timestamp'] = pd.to_datetime(df.timestamp).dt.strftime('%Y-%m-%d %H:%M:%S')
        with self.assertRaises(ValueError):
            read_uploaded_csv(df.to_csv(index=False).encode(), 'SPY')

    def test_bad_ohlc_rejected(self):
        df = self.frame[list(REQUIRED)].copy()
        df.loc[5,'high'] = 0.1
        with self.assertRaises(ValueError):
            read_uploaded_csv(df.to_csv(index=False).encode(), 'SPY')

    def test_wrong_symbol_and_bad_columns_rejected(self):
        with self.assertRaises(ValueError):
            read_uploaded_csv(self.raw, 'AAPL')
        with self.assertRaises(ValueError):
            read_uploaded_csv(b'timestamp,close\n2026-10-01,100', 'SPY')

    def test_upload_size_and_future_bars_rejected(self):
        with self.assertRaises(ValueError):
            read_uploaded_csv(b'0'* (MAX_BYTES+1), 'SPY')
        with self.assertRaises(ValueError):
            read_uploaded_csv(self.raw, 'SPY', now=datetime(2026,10,1,tzinfo=timezone.utc))

    def test_replay_prefix_is_causal(self):
        _, full = analyze_prefix(self.frame, len(self.frame))
        prefix, partial = analyze_prefix(self.frame, 85)
        self.assertEqual(len(prefix), 85)
        self.assertEqual(full['snapshots'][:85], partial['snapshots'])
        self.assertEqual([p for p in full['pivots'] if p['confirmed_index']<85], partial['pivots'])
        self.assertEqual([s for s in full['signals'] if s['signal_index']<85], partial['signals'])

    def test_invalid_cursor_rejected(self):
        for count in (0,-1,True,len(self.frame)+1):
            with self.assertRaises(ValueError):
                analyze_prefix(self.frame, count)


    def test_replay_manifest_is_deterministic_and_causal(self):
        prefix, _ = analyze_prefix(self.frame, 85)
        manifest = replay_manifest(prefix, self.meta)
        self.assertEqual(manifest_json(prefix, self.meta), manifest_json(prefix, self.meta))
        self.assertEqual(json.loads(manifest_json(prefix, self.meta)), manifest)
        self.assertEqual(manifest['visible_bars'], 85)
        self.assertFalse(manifest['orders_enabled'])
        self.assertFalse(manifest['feed_verified'])
        self.assertTrue(manifest['synthetic'])
        self.assertNotIn('input_sha256', {k for k,v in manifest.items() if v is not None})
        self.assertNotEqual(manifest['visible_ohlcv_sha256'],
                            replay_manifest(self.frame, self.meta)['visible_ohlcv_sha256'])

    def test_manifest_rejects_invalid_research_context(self):
        prefix, _ = analyze_prefix(self.frame, 10)
        with self.assertRaises(ValueError):
            replay_manifest(prefix, {**self.meta, 'orders_enabled': True})
        with self.assertRaises(ValueError):
            replay_manifest(prefix, {**self.meta, 'feed_verified': True})
        with self.assertRaises(ValueError):
            replay_manifest(prefix.iloc[:0], self.meta)



class EquityChartTests(unittest.TestCase):
    def test_regular_session_axis_removes_calendar_gaps_and_aligns_traces(self):
        from research_workspace.equity_ui import equity_chart
        frame, _ = synthetic_fixture('SPY')
        prefix, features = analyze_prefix(frame, 100)
        fig = equity_chart(prefix, features, 'SPY')
        bars = list(fig.data[0].x)
        volume = list(fig.data[1].x)
        self.assertEqual(len(bars), 100)
        self.assertEqual(bars, volume)
        self.assertEqual(len(bars), len(set(bars)))
        self.assertEqual(fig.layout.xaxis.type, 'category')
        self.assertEqual(fig.layout.xaxis2.type, 'category')
        self.assertEqual(list(fig.layout.xaxis2.categoryarray), bars)
        self.assertGreater(len(fig.layout.xaxis2.tickvals), 1)
        self.assertLess(len(fig.layout.xaxis2.tickvals), len(bars))
        for pivot_trace in fig.data[2:]:
            self.assertTrue(set(pivot_trace.x).issubset(set(bars)))

    def test_replay_axis_contains_only_visible_bars(self):
        from research_workspace.equity_ui import equity_chart
        frame, _ = synthetic_fixture('SPY')
        prefix, features = analyze_prefix(frame, 31)
        fig = equity_chart(prefix, features, 'SPY')
        self.assertEqual(len(fig.data[0].x), 31)
        self.assertEqual(list(fig.layout.xaxis2.categoryarray), list(fig.data[0].x))


class EquityUITests(unittest.TestCase):
    def app(self):
        from pathlib import Path
        from streamlit.testing.v1 import AppTest
        return AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=60)

    def test_synthetic_chart_is_visibly_labeled(self):
        at = self.app().run()
        at.radio(key='page').set_value('Equity Research').run()
        at.radio(key='equity_mode').set_value('Synthetic teaching example').run()
        self.assertFalse(at.exception)
        self.assertTrue(any('Sentetik veri' in x.value for x in at.warning))
        self.assertEqual(len(at.get('plotly_chart')), 1)

    def test_no_upload_means_no_chart(self):
        at = self.app().run()
        at.radio(key='page').set_value('Equity Research').run()
        at.radio(key='equity_mode').set_value('Upload my OHLCV CSV').run()
        self.assertFalse(at.exception)
        self.assertTrue(any('OHLCV dosyası seçin' in x.value for x in at.info))
        self.assertEqual(len(at.get('plotly_chart')), 0)

    def test_provider_mode_does_not_fetch_automatically(self):
        with patch('research_workspace.equity_ui.read_configured_alpaca_history') as fetch:
            at = self.app().run()
            at.radio(key='page').set_value('Equity Research').run()
            self.assertFalse(at.exception)
            self.assertEqual(at.radio(key='equity_mode').value, 'Alpaca historical (read-only)')
            self.assertTrue(any('Alpaca verisini yüklemek için' in x.value for x in at.info))
            self.assertEqual(len(at.get('plotly_chart')), 0)
            fetch.assert_not_called()

    def test_provider_refresh_failure_clears_previous_chart_and_hides_raw_error(self):
        frame, meta = synthetic_fixture('SPY')
        source = {**meta, 'synthetic': False, 'feed': 'iex', 'currency': 'USD',
                  'provider_api_response': True, 'origin': 'ALPACA API RESPONSE TEST FIXTURE'}
        original_get_option = st.get_option
        with patch('research_workspace.equity_ui.st.get_option',
                   side_effect=lambda key: '127.0.0.1' if key == 'server.address' else original_get_option(key)), \
             patch('research_workspace.equity_ui.alpaca_credentials_status', return_value='configured'), \
             patch('research_workspace.equity_ui._completed_session_window',
                   return_value=(date(2026, 10, 5), date(2026, 10, 16))), \
             patch('research_workspace.equity_ui.read_configured_alpaca_history', side_effect=[
                 (frame, source), EquityProviderError('SECRET_HEADER_CANARY', code='authentication')
             ]) as fetch:
            at = self.app().run()
            at.radio(key='page').set_value('Equity Research').run()
            fetch.assert_not_called()
            at.button(key='equity_load_provider').click().run()
            self.assertFalse(at.exception)
            fetch.assert_called_once_with('SPY', '2026-10-05', '2026-10-16', feed='iex')
            self.assertEqual(len(at.get('plotly_chart')), 1)
            self.assertTrue(any('Alpaca · IEX' in item.value for item in at.caption))
            at.button(key='equity_load_provider').click().run()
            self.assertFalse(at.exception)
            self.assertEqual(len(at.get('plotly_chart')), 0)
            self.assertTrue(any('anahtar çiftini reddetti' in item.value for item in at.error))
            self.assertTrue(all('SECRET_HEADER_CANARY' not in item.value for item in at.error))
            at.run()
            self.assertEqual(len(at.get('plotly_chart')), 0)
            self.assertEqual(fetch.call_count, 2)

    def test_changed_symbol_invalidates_cached_provider_source_without_another_request(self):
        frame, meta = synthetic_fixture('SPY')
        source = {**meta, 'synthetic': False, 'feed': 'iex',
                  'provider_api_response': True, 'origin': 'ALPACA API RESPONSE TEST FIXTURE'}
        original_get_option = st.get_option
        with patch('research_workspace.equity_ui.st.get_option',
                   side_effect=lambda key: '127.0.0.1' if key == 'server.address' else original_get_option(key)), \
             patch('research_workspace.equity_ui.alpaca_credentials_status', return_value='configured'), \
             patch('research_workspace.equity_ui._completed_session_window',
                   return_value=(date(2026, 10, 5), date(2026, 10, 16))), \
             patch('research_workspace.equity_ui.read_configured_alpaca_history',
                   return_value=(frame, source)) as fetch:
            at = self.app().run()
            at.radio(key='page').set_value('Equity Research').run()
            at.button(key='equity_load_provider').click().run()
            self.assertEqual(len(at.get('plotly_chart')), 1)
            for symbol in ('QQQ', 'SPY'):
                at.selectbox(key='equity_symbol').set_value(symbol).run()
                self.assertFalse(at.exception)
                self.assertEqual(len(at.get('plotly_chart')), 0)
            self.assertEqual(fetch.call_count, 1)

    def test_provider_defaults_use_completed_sessions_and_stop_before_seal(self):
        from research_workspace.equity_ui import _completed_session_window
        self.assertEqual(_completed_session_window(datetime(2026, 10, 23, 15, tzinfo=timezone.utc)),
                         (date(2026, 10, 16), date(2026, 10, 22)))
        self.assertEqual(_completed_session_window(datetime(2026, 11, 10, tzinfo=timezone.utc)),
                         (date(2026, 10, 19), date(2026, 10, 23)))

if __name__ == '__main__':
    unittest.main()
