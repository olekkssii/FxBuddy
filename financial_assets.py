from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from random import randint
from typing import Callable


RATES_TO_UAH: dict[str, float] = {
    "UAH": 1.0,
    "USD": 41.5,
    "EUR": 45.0,
    "GBP": 52.0,
    "PLN": 10.5,
    "BTC": 3_800_000.0,
}


@dataclass
class Asset(ABC):
    name: str
    amount: float

    def __post_init__(self) -> None:
        self.amount = float(self.amount)

    @abstractmethod
    def get_value_uah(self) -> float:
        """Return the asset value in Ukrainian hryvnia."""


class CurrencyAsset(Asset):
    def __init__(self, name: str, amount: float, rate_to_uah: float) -> None:
        super().__init__(name=name, amount=amount)
        self.__rate_to_uah = float(rate_to_uah)

    @property
    def rate(self) -> float:
        return self.__rate_to_uah

    def get_value_uah(self) -> float:
        return self.amount * self.__rate_to_uah


class CryptoAsset(Asset):
    def __init__(self, name: str, amount: float, base_rate_to_uah: float) -> None:
        super().__init__(name=name, amount=amount)
        self.base_rate_to_uah = float(base_rate_to_uah)

    def get_value_uah(self) -> float:
        volatile_rate = self.base_rate_to_uah + randint(-500, 500)
        return self.amount * volatile_rate


class Portfolio:
    def __init__(self) -> None:
        self.__assets: list[Asset] = []

    def add(self, asset: Asset) -> None:
        if not isinstance(asset, Asset):
            raise TypeError("Portfolio accepts only Asset instances")
        self.__assets.append(asset)

    def total_value_uah(self) -> float:
        return sum(asset.get_value_uah() for asset in self.__assets)


def _normalize_currency(currency: str) -> str:
    return currency.strip().upper()


def _get_rate_to_uah(currency: str) -> float:
    normalized = _normalize_currency(currency)
    try:
        return RATES_TO_UAH[normalized]
    except KeyError as exc:
        supported = ", ".join(sorted(RATES_TO_UAH))
        raise ValueError(f"Unsupported currency '{currency}'. Supported: {supported}") from exc


def convert_currency(amount: float, from_currency: str, to_currency: str) -> dict[str, float | str]:
    from_code = _normalize_currency(from_currency)
    to_code = _normalize_currency(to_currency)

    from_rate = _get_rate_to_uah(from_code)
    to_rate = _get_rate_to_uah(to_code)

    source_asset = CurrencyAsset(from_code, amount, from_rate)
    amount_uah = source_asset.get_value_uah()
    result = amount_uah / to_rate
    conversion_rate = from_rate / to_rate

    return {
        "from": from_code,
        "to": to_code,
        "amount": float(amount),
        "result": result,
        "rate": conversion_rate,
    }


FINANCIAL_AGENT_PROMPT = (
    "Ви є фінансовим консультантом з обміну валют. "
    "Конвертуйте суми між валютами та пояснюйте поточний курс. "
    "Відповідайте українською мовою."
)


@dataclass(frozen=True)
class FinancialAgent:
    prompt: str
    tools: tuple[Callable[..., dict[str, float | str]], ...]


financial_agent = FinancialAgent(
    prompt=FINANCIAL_AGENT_PROMPT,
    tools=(convert_currency,),
)
