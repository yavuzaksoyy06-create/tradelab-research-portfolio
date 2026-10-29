"""Offline historical-provider contract tests: no network and no execution."""
from datetime import datetime, timezone
import unittest

from research_workspace.equity_data import synthetic_fixture
from research_workspace.equity_provider import EquityProviderError, read_alpaca_history


class AlpacaEquityHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source, _ = synthetic_fixture("SPY")
        cls.payload = [
            {"t": row.timestamp.isoformat(), "o": row.open, "h": row.high,
             "l": row.low, "c": row.close, "v": row.volume}
            for row in cls.source.itertuples(index=False)
        ]
        cls.now = datetime(2026, 10, 27, tzinfo=timezone.utc)

    def load(self, request_page, **overrides):
        args = {
            "symbol": "SPY", "start": "2026-10-05", "end": "2026-10-16",
            "feed": "iex", "api_key": "redacted-key", "api_secret": "redacted-secret",
            "now": self.now, "request_page": request_page,
        }
        args.update(overrides)
        return read_alpaca_history(args.pop("symbol"), args.pop("start"), args.pop("end"), **args)

    def test_full_history_is_validated_and_unverified(self):
        calls = []
        def fake(params, key, secret):
            calls.append(params)
            self.assertEqual(key, "redacted-key")
            self.assertEqual(secret, "redacted-secret")
            self.assertEqual(params["feed"], "iex")
            self.assertEqual(params["adjustment"], "split")
            self.assertEqual(params["timeframe"], "15Min")
            return {"bars": {"SPY": self.payload}, "next_page_token": None}

        frame, meta = self.load(fake)
        self.assertEqual(len(frame), len(self.source))
        self.assertEqual(len(calls), 1)
        self.assertTrue(meta["provider_api_response"])
        self.assertEqual(meta["feed"], "iex")
        self.assertFalse(meta["feed_verified"])
        self.assertFalse(meta["point_in_time_archive_verified"])
        self.assertFalse(meta["orders_enabled"])
        self.assertNotIn("redacted-secret", str(meta))

    def test_multiple_pages_are_required(self):
        def fake(params, key, secret):
            if "page_token" not in params:
                return {"bars": {"SPY": self.payload[:120]}, "next_page_token": "next"}
            self.assertEqual(params["page_token"], "next")
            return {"bars": {"SPY": self.payload[120:]}, "next_page_token": None}
        frame, _ = self.load(fake)
        self.assertEqual(len(frame), len(self.source))

    def test_missing_bar_rejected(self):
        with self.assertRaises(ValueError):
            self.load(lambda *_: {"bars": {"SPY": self.payload[1:]}, "next_page_token": None})

    def test_out_of_order_and_duplicate_bars_rejected(self):
        swapped = list(self.payload)
        swapped[10], swapped[11] = swapped[11], swapped[10]
        for bad in (swapped, self.payload[:10] + self.payload[9:]):
            with self.subTest(case="out-of-order or duplicate"), self.assertRaises(ValueError):
                self.load(lambda *_: {"bars": {"SPY": bad}, "next_page_token": None})

    def test_out_of_session_rows_are_explicitly_excluded(self):
        overnight = {"t": "2026-10-05T08:00:00Z", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}
        frame, meta = self.load(
            lambda *_: {"bars": {"SPY": [overnight] + self.payload}, "next_page_token": None}
        )
        self.assertEqual(len(frame), len(self.source))
        self.assertEqual(meta["outside_regular_session_bars_excluded"], 1)

    def test_bad_feed_future_date_missing_credentials_fail_without_transport(self):
        def no_network(*_):
            self.fail("Transport should never be called")
        for update in (
            {"feed": "boats"},
            {"symbol": "AAPL"},
            {"api_secret": ""},
            {"start": "2026-10-20", "end": "2026-10-29"},
            {"start": "2026-10-16", "end": "2026-10-05"},
        ):
            with self.subTest(update=update), self.assertRaises(ValueError):
                self.load(no_network, **update)

    def test_provider_schema_and_page_token_guards(self):
        bad_responses = [
            {"bars": {"QQQ": self.payload}, "next_page_token": None},
            {"bars": {"SPY": {}}, "next_page_token": None},
            {"bars": {"SPY": [{"t": "2026-10-05T13:30:00Z"}]}, "next_page_token": None},
        ]
        for result in bad_responses:
            with self.subTest(result=str(result)[:40]), self.assertRaises(EquityProviderError):
                self.load(lambda *_: result)
        with self.assertRaises(EquityProviderError):
            self.load(lambda *_: {"bars": {"SPY": []}, "next_page_token": "same"})

    def test_provider_empty_response_is_not_a_chart(self):
        with self.assertRaises(EquityProviderError):
            self.load(lambda *_: {"bars": {"SPY": []}, "next_page_token": None})


if __name__ == "__main__":
    unittest.main()
