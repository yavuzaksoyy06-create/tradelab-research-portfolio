"""Stage 6 equity data checks: offline, no feeds and no order endpoints."""
from datetime import datetime, timezone
import unittest

import pandas as pd

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


if __name__ == '__main__':
    unittest.main()
