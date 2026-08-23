"""Telegramで受信した売買報告メッセージのパース。

フォーマット(要調整可):
  買 <証券コード> <購入価格> <株数>   例: 買 7203 2500 100
  売 <証券コード> <売却価格>          例: 売 7203 2600
"""

import re
from dataclasses import dataclass

_BUY_RE = re.compile(r"^買\s+(\d{4})\s+([\d.]+)\s+(\d+)$")
_SELL_RE = re.compile(r"^売\s+(\d{4})\s+([\d.]+)$")


@dataclass
class BuyReport:
    ticker_code: str
    price: float
    quantity: int


@dataclass
class SellReport:
    ticker_code: str
    price: float


def parse_message(text: str) -> BuyReport | SellReport | None:
    text = text.strip()

    m = _BUY_RE.match(text)
    if m:
        code, price, quantity = m.groups()
        return BuyReport(ticker_code=code, price=float(price), quantity=int(quantity))

    m = _SELL_RE.match(text)
    if m:
        code, price = m.groups()
        return SellReport(ticker_code=code, price=float(price))

    return None
