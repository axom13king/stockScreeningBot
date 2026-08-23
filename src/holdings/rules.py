"""保有銘柄の売り時判定ルール。

具体的な閾値・ルールは未確定。まずは代表的な2ルールを拡張可能な形で実装し、
運用しながら追加・調整する想定。
"""

from dataclasses import dataclass


@dataclass
class SellSignal:
    ticker_code: str
    reason: str


# TODO: 運用しながら閾値を調整する
TARGET_PROFIT_RATIO = 0.15   # 購入価格から+15%で利確シグナル
STOP_LOSS_RATIO = -0.08      # 購入価格から-8%で損切りシグナル


def check_target_profit(holding: dict, current_price: float) -> SellSignal | None:
    ratio = (current_price - holding["buy_price"]) / holding["buy_price"]
    if ratio >= TARGET_PROFIT_RATIO:
        return SellSignal(holding["ticker_code"], f"目標株価到達(+{ratio:.1%})")
    return None


def check_stop_loss(holding: dict, current_price: float) -> SellSignal | None:
    ratio = (current_price - holding["buy_price"]) / holding["buy_price"]
    if ratio <= STOP_LOSS_RATIO:
        return SellSignal(holding["ticker_code"], f"損切りライン到達({ratio:.1%})")
    return None


SELL_RULES = [check_target_profit, check_stop_loss]


def evaluate_sell_signals(holding: dict, current_price: float) -> list[SellSignal]:
    signals = []
    for rule in SELL_RULES:
        signal = rule(holding, current_price)
        if signal:
            signals.append(signal)
    return signals
