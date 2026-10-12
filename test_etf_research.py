"""Offline, deterministic regression tests for the v1.8 ETF research route."""
import unittest
import pandas as pd
from etf_research import (
    clean_ticker, is_etf_type, performance, assessment, _fund_rows,
    _sector_rows, _annualized_return,
)

class ETFResearchTests(unittest.TestCase):
    def test_symbol_normalization(self):
        self.assertEqual(clean_ticker(" qqqm "), "QQQM")
        with self.assertRaises(ValueError):
            clean_ticker("QQQM;rm")

    def test_automatic_type_detection(self):
        self.assertTrue(is_etf_type("VOO", {"quoteType": "ETF"}))
        self.assertTrue(is_etf_type("QQQM", {}))
        self.assertTrue(is_etf_type("SCHD", {}))
        self.assertFalse(is_etf_type("AAPL", {"quoteType": "EQUITY"}))
        self.assertFalse(is_etf_type("VOO", {"quoteType": "EQUITY"}))
        self.assertFalse(is_etf_type("MSFT", {}))

    def test_holdings_and_sector_weights(self):
        sample = pd.DataFrame({
            "Holding Name": ["Company A", "Company B", "Company C"],
            "Holding Percent": [0.12, 0.07, None],
        }, index=["AAA","BBB","CCC"])
        holdings = _fund_rows(sample, ("Holding Percent",), ("Holding Name",))
        self.assertEqual(len(holdings), 2)
        self.assertAlmostEqual(holdings[0]["weight"], 0.12)
        sectors = _sector_rows({"technology":0.42,"healthcare":0.15,"unused":None})
        self.assertEqual(sectors[0]["name"], "Technology")
        self.assertAlmostEqual(sectors[0]["weight"], 0.42)

    def test_performance_does_not_claim_nonexistent_history(self):
        dates = pd.date_range("2024-01-02", "2025-12-31", freq="B")
        series = pd.Series([100 + i * .1 for i in range(len(dates))], index=dates)
        result = performance(pd.DataFrame({"Adj Close":series, "Close":series}))
        self.assertIsNotNone(result["returns"][1])
        self.assertIsNone(result["returns"][3])
        self.assertIsNone(result["returns"][5])
        self.assertLessEqual(result["max_drawdown"], 0)

    def test_drawdowns_are_negative(self):
        dates = pd.to_datetime(["2023-01-01","2023-01-02","2023-01-03"])
        result = performance(pd.DataFrame({"Close":[100, 80, 95]}, index=dates))
        self.assertAlmostEqual(result["max_drawdown"], -20)
        self.assertIn("dividends excluded", result["method"])

    def test_unavailable_data_is_not_automatically_buy(self):
        result = assessment({"expense_ratio":None, "holdings":[], "performance":{"returns":{}}})
        self.assertEqual(result["verdict"], "WATCH")
        self.assertEqual(result["coverage"], "Limited")
        self.assertIsNone(result["top_ten"])

    def test_expensive_fund_is_pass_even_with_missing_history(self):
        result = assessment({"expense_ratio":0.012, "holdings":[],
                             "performance":{"returns":{}}})
        self.assertEqual(result["verdict"], "PASS")

    def test_strict_buy_screen(self):
        holdings = [{"weight":.03}] * 10
        result = assessment({"expense_ratio":.0003,"holdings":holdings,
                             "performance":{"returns":{5:7.8}}})
        self.assertEqual(result["verdict"], "BUY")
        self.assertEqual(result["coverage"], "Good")
        self.assertAlmostEqual(result["top_ten"], 0.3)

    def test_concentration_rejects_extreme_exposure(self):
        holdings = [{"weight":.08}] * 10
        result = assessment({"expense_ratio":.0003,"holdings":holdings,
                             "performance":{"returns":{5:8}}})
        self.assertEqual(result["verdict"], "PASS")

    def test_midrange_hold_screen(self):
        holdings = [{"weight":.05}] * 10
        result = assessment({"expense_ratio":.002, "holdings":holdings,
                             "performance":{"returns":{5:5.0}}})
        self.assertEqual(result["verdict"], "HOLD")

if __name__ == "__main__":
    unittest.main()
