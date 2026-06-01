from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from financial_assets import RATES_TO_UAH, convert_currency


HOST = "127.0.0.1"
PORT = int(os.environ.get("PORT", "8000"))
ROOT = Path(__file__).resolve().parent
OPENAI_RESPONSES_URL = os.environ.get("OPENAI_RESPONSES_URL", "https://api.openai.com/v1/responses")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.2")
MAX_MESSAGE_LENGTH = 600

FINANCE_ONLY_REPLY = (
    "Я можу допомагати тільки з фінансовими питаннями в цьому додатку: "
    "валюти, конвертація, портфель, активи, криптовалюти та фінансові розрахунки."
)

LOCAL_ONLY_REPLY = (
    "Зараз можу виконувати локальну конвертацію валют. Напишіть, наприклад: "
    "100 USD в EUR або 100 дол в гривні."
)

SYSTEM_INSTRUCTIONS = f"""
Ти фінансовий AI-агент для навчального додатку обміну валют.
Відповідай українською мовою, коротко і практично.

Дозволені теми: валюти, конвертація, фіксовані курси, портфель активів,
CurrencyAsset, CryptoAsset, базові фінансові поняття, ризики та фінансові розрахунки.

Заборонені теми: усе, що не стосується фінансів. Якщо користувач просить щось інше,
відмовся і скажи, що можеш допомагати тільки з фінансовими питаннями в цьому додатку.

Не давай персональних інвестиційних рекомендацій на кшталт "купуй", "продавай",
"вклади всі гроші". Можна пояснювати ризики, формули й можливі сценарії.

Використовуй тільки фіксовані курси додатку до UAH:
{json.dumps(RATES_TO_UAH, ensure_ascii=False)}
""".strip()

FINANCE_KEYWORDS = {
    "asset",
    "btc",
    "bitcoin",
    "бакс",
    "crypto",
    "currency",
    "eur",
    "gbp",
    "portfolio",
    "uah",
    "usd",
    "актив",
    "акції",
    "банк",
    "біткоїн",
    "валют",
    "грив",
    "грн",
    "депозит",
    "долар",
    "дол",
    "дохід",
    "євро",
    "інвест",
    "конверт",
    "крипт",
    "курс",
    "обмін",
    "портф",
    "прибут",
    "ризик",
    "фінанс",
    "фунт",
}

CURRENCY_ALIASES = {
    "USD": ("usd", "доларів", "долари", "долар", "дол", "баксів", "бакси", "бакс"),
    "EUR": ("eur", "євро", "евро"),
    "GBP": ("gbp", "фунтів", "фунти", "фунт"),
    "BTC": ("btc", "bitcoin", "біткоїнів", "біткоїн", "биткоин"),
    "UAH": ("uah", "гривень", "гривні", "гривня", "грн"),
}

CURRENCY_ALIASES.update(
    {
        "USD": (*CURRENCY_ALIASES["USD"], "доларів", "долари", "долара", "долару", "долар", "дол", "баксів", "бакси", "бакс"),
        "EUR": (*CURRENCY_ALIASES["EUR"], "євро", "евро", "євр", "евр"),
        "GBP": (*CURRENCY_ALIASES["GBP"], "фунтів", "фунти", "фунт"),
        "PLN": ("pln", "злотих", "злоті", "злотий", "злотого", "злот"),
        "BTC": (*CURRENCY_ALIASES["BTC"], "біткоїнів", "біткоїн", "биткоин"),
        "UAH": (*CURRENCY_ALIASES["UAH"], "гривень", "гривні", "гривня", "грн"),
    }
)

FINANCE_KEYWORDS.update(
    {
        "банк",
        "валют",
        "грив",
        "грн",
        "депозит",
        "дохід",
        "злот",
        "інвест",
        "інфляц",
        "конверт",
        "кредит",
        "крипт",
        "курс",
        "обмін",
        "подат",
        "портф",
        "прибут",
        "ризик",
        "ставк",
        "фінанс",
    }
)


def load_env_file(path: Path = ROOT / ".env") -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def is_greeting_message(message: str) -> bool:
    normalized = re.sub(r"[!?.,\s]+", " ", message.lower()).strip()
    return normalized in {"привіт", "вітаю", "добрий день", "доброго дня", "hello", "hi", "hey"}


def is_history_request(message: str) -> bool:
    normalized = message.lower()
    has_history_word = re.search(r"нагадай|покажи|згадай|останні|минул|попередн|істор", normalized)
    has_exchange_word = re.search(r"обмін|конвертац|курс|операц", normalized)
    return bool(has_history_word and has_exchange_word)


def find_currency_matches(message: str) -> list[tuple[int, int, str]]:
    normalized = message.lower()
    matches: list[tuple[int, int, str]] = []

    for code, aliases in CURRENCY_ALIASES.items():
        for alias in aliases:
            for match in re.finditer(rf"(?<!\w){re.escape(alias)}(?!\w)", normalized):
                matches.append((match.start(), match.end(), code))

    matches.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    result: list[tuple[int, int, str]] = []
    used_ranges: list[tuple[int, int]] = []

    for start, end, code in matches:
        if any(start < used_end and end > used_start for used_start, used_end in used_ranges):
            continue

        result.append((start, end, code))
        used_ranges.append((start, end))

    return result


def find_currencies(message: str) -> list[str]:
    return [code for _, _, code in find_currency_matches(message)]


def is_finance_message(message: str) -> bool:
    normalized = message.lower()
    return (
        bool(find_currencies(message))
        or is_history_request(message)
        or any(keyword in normalized for keyword in FINANCE_KEYWORDS)
    )


def parse_local_conversion(message: str) -> tuple[float, str, str] | None:
    currencies = find_currency_matches(message)

    amount_match = re.search(r"\d+(?:[.,]\d+)?", message)
    amount = float(amount_match.group(0).replace(",", ".")) if amount_match else 1.0

    if len(currencies) == 1 and currencies[0][2] != "UAH":
        return amount, currencies[0][2], "UAH"

    if len(currencies) < 2:
        return None

    if amount_match:
        amount_start = amount_match.start()
        amount_end = amount_match.end()
        from_after_amount = next((item for item in currencies if item[0] >= amount_end), None)

        if from_after_amount:
            from_code = from_after_amount[2]
            to_after_from = next(
                (item for item in currencies if item[0] > from_after_amount[1] and item[2] != from_code),
                None,
            )
            to_before_amount = next(
                (item for item in currencies if item[1] <= amount_start and item[2] != from_code),
                None,
            )
            fallback_to = next((item for item in currencies if item[2] != from_code), None)
            to_currency = to_after_from or to_before_amount or fallback_to

            if to_currency:
                return amount, from_code, to_currency[2]

    return amount, currencies[0][2], currencies[1][2]


def format_decimal(value: float) -> str:
    formatted = f"{value:,.6f}".rstrip("0").rstrip(".")
    return formatted.replace(",", " ")


def get_requested_history_count(message: str) -> int:
    normalized = message.lower()
    number_match = re.search(r"\d+", normalized)

    if number_match:
        return min(max(int(number_match.group(0)), 1), 20)

    word_numbers = {
        "один": 1,
        "одну": 1,
        "два": 2,
        "дві": 2,
        "три": 3,
        "чотири": 4,
        "п'ять": 5,
        "пять": 5,
    }

    for word, value in word_numbers.items():
        if word in normalized:
            return value

    return 5


def sanitize_history(raw_history: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_history, list):
        return []

    result: list[dict[str, Any]] = []

    for item in raw_history[:20]:
        if not isinstance(item, dict):
            continue

        try:
            result.append(
                {
                    "amount": float(item["amount"]),
                    "from": str(item["from"]).upper(),
                    "result": float(item["result"]),
                    "to": str(item["to"]).upper(),
                    "rate": float(item["rate"]),
                }
            )
        except (KeyError, TypeError, ValueError):
            continue

    return result


def build_history_reply(message: str, history: list[dict[str, Any]]) -> str:
    count = get_requested_history_count(message)
    items = history[:count]

    if not items:
        return "Поки немає збережених обмінів. Зробіть конвертацію, і я зможу її нагадати."

    lines = []

    for index, item in enumerate(items, start=1):
        lines.append(
            f"{index}. {format_decimal(item['amount'])} {item['from']} = "
            f"{format_decimal(item['result'])} {item['to']}. "
            f"Курс: 1 {item['from']} = {format_decimal(item['rate'])} {item['to']}."
        )

    return "\n".join(lines)


def build_local_conversion_reply(message: str) -> str | None:
    parsed = parse_local_conversion(message)

    if not parsed:
        return None

    amount, from_currency, to_currency = parsed
    conversion = convert_currency(amount, from_currency, to_currency)

    return (
        f"{format_decimal(conversion['amount'])} {conversion['from']} = "
        f"{format_decimal(conversion['result'])} {conversion['to']}. "
        f"Курс: 1 {conversion['from']} = {format_decimal(conversion['rate'])} {conversion['to']}."
    )


def extract_response_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str) and payload["output_text"].strip():
        return payload["output_text"].strip()

    text_parts: list[str] = []

    for item in payload.get("output", []):
        if not isinstance(item, dict):
            continue

        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue

            text = content.get("text") or content.get("refusal")

            if isinstance(text, str) and text.strip():
                text_parts.append(text.strip())

    return "\n".join(text_parts).strip()


def call_openai(message: str, history: list[dict[str, Any]] | None = None) -> str | None:
    api_key = os.environ.get("OPENAI_API_KEY")

    if not api_key:
        return None

    input_text = message

    if history:
        history_context = build_history_reply("нагадай 10 минулих обмінів", history)
        input_text = f"Останні обміни користувача:\n{history_context}\n\nЗапит користувача:\n{message}"

    request_body = {
        "model": os.environ.get("OPENAI_MODEL", OPENAI_MODEL),
        "instructions": SYSTEM_INSTRUCTIONS,
        "input": input_text,
        "max_output_tokens": 350,
        "store": False,
    }

    request = urllib.request.Request(
        os.environ.get("OPENAI_RESPONSES_URL", OPENAI_RESPONSES_URL),
        data=json.dumps(request_body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API returned {error.code}: {details}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"OpenAI API is unavailable: {error.reason}") from error

    reply = extract_response_text(payload)

    if not reply:
        raise RuntimeError("OpenAI API returned an empty response.")

    return reply


def build_chat_reply(message: str, history: Any = None) -> dict[str, str]:
    cleaned_message = message.strip()[:MAX_MESSAGE_LENGTH]
    cleaned_history = sanitize_history(history)

    if not cleaned_message:
        return {"reply": "Напишіть фінансове питання або запит на конвертацію.", "source": "validation"}

    if is_greeting_message(cleaned_message):
        return {
            "reply": "Привіт. Я фінансовий агент: можу конвертувати валюти, показати курс, нагадати минулі обміни й пояснити базові фінансові поняття.",
            "source": "greeting",
        }

    if is_history_request(cleaned_message):
        return {"reply": build_history_reply(cleaned_message, cleaned_history), "source": "history"}

    local_reply = build_local_conversion_reply(cleaned_message)

    if local_reply:
        return {"reply": local_reply, "source": "local"}

    if not is_finance_message(cleaned_message):
        return {"reply": FINANCE_ONLY_REPLY, "source": "blocked"}

    ai_reply = call_openai(cleaned_message, cleaned_history)

    if ai_reply:
        return {"reply": ai_reply, "source": "openai"}

    return {"reply": LOCAL_ONLY_REPLY, "source": "local"}


class FinanceChatHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_POST(self) -> None:
        if self.path != "/api/chat":
            self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return

        try:
            payload = self.read_json()
            reply = build_chat_reply(str(payload.get("message", "")), payload.get("history", []))
        except RuntimeError as error:
            self.send_json({"error": str(error)}, HTTPStatus.BAD_GATEWAY)
            return
        except (json.JSONDecodeError, ValueError) as error:
            self.send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            return

        self.send_json(reply)

    def read_json(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))

        if content_length <= 0:
            raise ValueError("Request body is empty.")

        if content_length > 32768:
            raise ValueError("Request body is too large.")

        raw_body = self.rfile.read(content_length).decode("utf-8")
        payload = json.loads(raw_body)

        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object.")

        return payload

    def send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        response = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)


def main() -> None:
    load_env_file()
    port = int(os.environ.get("PORT", str(PORT)))
    server = ThreadingHTTPServer((HOST, port), FinanceChatHandler)
    print(f"Serving http://{HOST}:{port}")
    print("AI chat endpoint: /api/chat")
    server.serve_forever()


if __name__ == "__main__":
    main()
