"""保有銘柄ごとの市場感応度(ベータ)・売りルールまでの余力分析。

market_risk.py の判定は「市場全体が危ないかどうか」しか教えてくれないため、
「保有している個別銘柄が、その市場の動きにどれだけ敏感か」を補う。
ベータが高い銘柄ほど市場の下落に連動しやすく、売りルール(損切り・トレーリングストップ)
までの余力が小さい銘柄ほど、その日のうちに引っかかるリスクが高い。
"""

import pandas as pd

from src.holdings.rules import STOP_LOSS_RATIO, TRAILING_STOP_RATIO

BETA_LOOKBACK_DAYS = 60  # 約3ヶ月分の日次リターンでベータを計算
BETA_HIGH_THRESHOLD = 1.3   # これ以上は「高感応度」
BETA_LOW_THRESHOLD = 0.8    # これ未満は「低感応度」(その間は「標準」)


def compute_beta(stock_prices: pd.DataFrame, topix_prices: pd.DataFrame, window: int = BETA_LOOKBACK_DAYS) -> float | None:
    """直近window営業日の日次リターンから、TOPIXに対するベータを計算する。

    ベータ1.0=市場と同じ値動き、1.0超=市場より大きく動く(ハイベータ)、
    1.0未満=市場より小さく動く(ディフェンシブ)の目安。
    """
    stock_ret = stock_prices["Close"].pct_change().tail(window)
    topix_ret = topix_prices["Close"].pct_change().reindex(stock_ret.index)

    combined = pd.concat([stock_ret, topix_ret], axis=1, keys=["stock", "topix"]).dropna()
    if len(combined) < window // 2:
        return None

    variance = combined["topix"].var()
    if not variance:
        return None
    return float(combined["stock"].cov(combined["topix"]) / variance)


def beta_label(beta: float) -> str:
    if beta >= BETA_HIGH_THRESHOLD:
        return "高感応度"
    if beta >= BETA_LOW_THRESHOLD:
        return "標準"
    return "低感応度"


def analyze_holding(holding: dict, current_price: float, stock_prices: pd.DataFrame, topix_prices: pd.DataFrame) -> dict:
    """保有銘柄1件分の市場感応度・損切り/トレーリングストップまでの余力をまとめる。"""
    beta = compute_beta(stock_prices, topix_prices)
    pnl_ratio = (current_price - holding["buy_price"]) / holding["buy_price"]

    # 損切りラインまでの余力(pt)。マイナスなら既に損切り水準を割っている。
    stop_loss_cushion = (pnl_ratio - STOP_LOSS_RATIO) * 100

    trailing_cushion = None
    since_buy = stock_prices.loc[holding["buy_date"] :]
    if not since_buy.empty:
        peak = float(since_buy["Close"].max())
        if peak > 0:
            drawdown_from_peak = (current_price - peak) / peak
            trailing_cushion = (drawdown_from_peak - (-TRAILING_STOP_RATIO)) * 100

    return {
        "beta": beta,
        "beta_label": beta_label(beta) if beta is not None else "不明",
        "pnl_pct": pnl_ratio * 100,
        "stop_loss_cushion": stop_loss_cushion,
        "trailing_cushion": trailing_cushion,
    }
