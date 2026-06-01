import unittest
from unittest.mock import patch

from financial_assets import (
    CryptoAsset,
    CurrencyAsset,
    Portfolio,
    convert_currency,
    financial_agent,
)


class FinancialAssetsTest(unittest.TestCase):
    def test_currency_asset_value_uses_private_rate(self) -> None:
        asset = CurrencyAsset("USD", 100, 41.5)

        self.assertEqual(asset.rate, 41.5)
        self.assertEqual(asset.get_value_uah(), 4150.0)

    def test_crypto_asset_value_uses_volatile_rate(self) -> None:
        asset = CryptoAsset("BTC", 0.5, 3_800_000)

        with patch("financial_assets.randint", return_value=500):
            self.assertEqual(asset.get_value_uah(), 1_900_250.0)

    def test_portfolio_uses_polymorphic_asset_values(self) -> None:
        portfolio = Portfolio()
        portfolio.add(CurrencyAsset("USD", 100, 41.5))
        portfolio.add(CurrencyAsset("EUR", 10, 45.0))

        self.assertEqual(portfolio.total_value_uah(), 4600.0)

    def test_convert_currency_returns_conversion_payload(self) -> None:
        result = convert_currency(100, "usd", "eur")

        self.assertEqual(result["from"], "USD")
        self.assertEqual(result["to"], "EUR")
        self.assertEqual(result["amount"], 100.0)
        self.assertAlmostEqual(result["result"], 92.2222222222)
        self.assertAlmostEqual(result["rate"], 41.5 / 45.0)

    def test_financial_agent_has_prompt_and_tool(self) -> None:
        self.assertIn("українською мовою", financial_agent.prompt)
        self.assertIn(convert_currency, financial_agent.tools)


if __name__ == "__main__":
    unittest.main()
