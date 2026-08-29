"""保有銘柄の売り時判定ルール。

単純な損益率(利確/損切りライン)に加えて、スイングスクリーニングと同じ指標計算
(src/screening/swing/indicators.py の compute_metrics)を再利用したテクニカル指標
ベースのシグナルも評価する。閾値は仮値であり、運用しながら調整する想定。
"""

import pandas as pd
from dataclasses import dataclass

# TODO: 運用しながら閾値を調整する
TARGET_PROFIT_RATIO = 0.15    # 購入価格から+15%で利確シグナル
STOP_LOSS_RATIO = -0.08       # 購入価格から-8%で損切りシグナル
TRAILING_STOP_RATIO = 0.10    # 保有中の最高値からこの比率以上下落したらシグナル
RSI_OVERHEAT_THRESHOLD = 70   # RSIがこれ以上で「過熱・利確検討」


@dataclass
class SellSignal:
    ticker_code: str
    reason: str


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


def check_trailing_stop(holding: dict, current_price: float, price_history: pd.DataFrame) -> SellSignal | None:
    """購入日以降の最高値からの下落率で判定する(固定ラインではなく高値を追随)。"""
    since_buy = price_history.loc[holding["buy_date"] :]
    if since_buy.empty:
        return None
    peak = float(since_buy["Close"].max())
    if peak <= 0:
        return None
    drawdown = (current_price - peak) / peak
    if drawdown <= -TRAILING_STOP_RATIO:
        return SellSignal(holding["ticker_code"], f"高値{peak:.0f}円から{drawdown:.1%}下落(トレーリングストップ)")
    return None


def check_ma25_breakdown(holding: dict, current_price: float, metrics: dict) -> SellSignal | None:
    """25MA割れ: 単純な%ではなくトレンド崩壊の兆候として評価する。"""
    ma25 = metrics.get("ma25")
    if ma25 is None:
        return None
    if current_price < ma25:
        return SellSignal(holding["ticker_code"], f"25MA({ma25:.0f}円)割れ")
    return None


def check_ma5_below_ma25(holding: dict, current_price: float, metrics: dict) -> SellSignal | None:
    """短期トレンド転換: 5MAが25MAを下回った状態。"""
    ma5, ma25 = metrics.get("ma5"), metrics.get("ma25")
    if ma5 is None or ma25 is None:
        return None
    if ma5 < ma25:
        return SellSignal(holding["ticker_code"], f"短期トレンド転換(5MA{ma5:.0f} < 25MA{ma25:.0f})")
    return None


def check_rsi_overheat(holding: dict, current_price: float, metrics: dict) -> SellSignal | None:
    """RSI過熱: 短期的な買われすぎで利益確定を検討する目安。"""
    rsi = metrics.get("rsi")
    if rsi is None:
        return None
    if rsi >= RSI_OVERHEAT_THRESHOLD:
        return SellSignal(holding["ticker_code"], f"RSI過熱(RSI {rsi:.0f})、利確検討")
    return None


_BASIC_RULES = [check_target_profit, check_stop_loss]
_TECHNICAL_RULES = [check_ma25_breakdown, check_ma5_below_ma25, check_rsi_overheat]


def evaluate_sell_signals(
    holding: dict,
    current_price: float,
    price_history: pd.DataFrame,
    metrics: dict | None = None,
) -> list[SellSignal]:
    """損益率ベースのルールは常に評価し、指標(metrics)が計算できた場合のみ
    テクニカル指標ベースのルールも追加で評価する(データ不足の新規銘柄等はスキップ)。
    """
    signals = []

    for rule in _BASIC_RULES:
        signal = rule(holding, current_price)
        if signal:
            signals.append(signal)

    trailing_signal = check_trailing_stop(holding, current_price, price_history)
    if trailing_signal:
        signals.append(trailing_signal)

    if metrics:
        for rule in _TECHNICAL_RULES:
            signal = rule(holding, current_price, metrics)
            if signal:
                signals.append(signal)

    return signals
