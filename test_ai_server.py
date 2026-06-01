import unittest

from ai_server import build_chat_reply, build_local_conversion_reply, is_finance_message


class AiServerTest(unittest.TestCase):
    def test_finance_filter_allows_currency_request(self) -> None:
        self.assertTrue(is_finance_message("Скільки буде 100 USD в EUR?"))

    def test_finance_filter_blocks_unrelated_request(self) -> None:
        self.assertFalse(is_finance_message("Напиши рецепт піци"))

    def test_local_conversion_reply_uses_fixed_rates(self) -> None:
        reply = build_local_conversion_reply("100 USD в EUR")

        self.assertIsNotNone(reply)
        self.assertIn("100 USD", reply or "")
        self.assertIn("92.222222 EUR", reply or "")

    def test_local_conversion_reply_accepts_ukrainian_short_currency_names(self) -> None:
        reply = build_local_conversion_reply("привіт 100 дол в гривні")

        self.assertIsNotNone(reply)
        self.assertIn("100 USD", reply or "")
        self.assertIn("4 150 UAH", reply or "")

    def test_local_conversion_reply_accepts_typo_like_short_eur_request(self) -> None:
        reply = build_local_conversion_reply("скльки 100 євр в грн")

        self.assertIsNotNone(reply)
        self.assertIn("100 EUR", reply or "")
        self.assertIn("4 500 UAH", reply or "")

    def test_local_conversion_reply_supports_pln_rate(self) -> None:
        reply = build_local_conversion_reply("який курс злотого до гривні")

        self.assertIsNotNone(reply)
        self.assertIn("1 PLN", reply or "")
        self.assertIn("10.5 UAH", reply or "")

    def test_local_conversion_defaults_single_currency_to_uah(self) -> None:
        reply = build_local_conversion_reply("курс долара")

        self.assertIsNotNone(reply)
        self.assertIn("1 USD", reply or "")
        self.assertIn("41.5 UAH", reply or "")

    def test_chat_reply_allows_plain_greeting(self) -> None:
        reply = build_chat_reply("Привіт")

        self.assertEqual(reply["source"], "greeting")

    def test_chat_reply_can_remind_previous_exchanges(self) -> None:
        history = [
            {"amount": 100, "from": "USD", "result": 4150, "to": "UAH", "rate": 41.5},
            {"amount": 50, "from": "EUR", "result": 2250, "to": "UAH", "rate": 45},
            {"amount": 1, "from": "PLN", "result": 10.5, "to": "UAH", "rate": 10.5},
        ]
        reply = build_chat_reply("нагадай два минулих обміни", history)

        self.assertEqual(reply["source"], "history")
        self.assertIn("1. 100 USD", reply["reply"])
        self.assertIn("2. 50 EUR", reply["reply"])
        self.assertNotIn("3. 1 PLN", reply["reply"])

    def test_chat_reply_blocks_non_finance_before_ai_call(self) -> None:
        reply = build_chat_reply("Напиши вірш про кота")

        self.assertEqual(reply["source"], "blocked")


if __name__ == "__main__":
    unittest.main()
