"""スイングスクリーニング用の1銘柄あたりの指標計算。

価格履歴DataFrame(Open/High/Low/Close/Volume, DateIndex昇順)と評価基準日(as_of)を受け取り、
as_of時点で「その日までのデータだけ」を使って各種指標を計算する
(バックテストでの未来参照(lookahead)を防ぐため)。
"""

import pandas as pd


def _rsi(closes: pd.Series, period: int) -> pd.Series:
    delta = closes.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def compute_metrics(prices: pd.DataFrame, as_of: pd.Timestamp, cfg: dict) -> dict | None:
    """as_of時点までのデータで各種指標を計算する。データ不足なら None。"""
    hist = prices.loc[:as_of]
    if len(hist) < 90:  # MA50+20日前比較・60日高値などに必要な最低日数
        return None

    closes = hist["Close"]
    volumes = hist["Volume"]

    ma5 = closes.rolling(5).mean()
    ma25 = closes.rolling(25).mean()
    ma50 = closes.rolling(50).mean()
    rsi = _rsi(closes, cfg["rsi"]["period"])

    ma25_ago = cfg["trend"]["ma25_compare_days_ago"]
    ma50_ago = cfg["trend"]["ma50_compare_days_ago"]
    ma5_ago = cfg["pullback"]["ma5_compare_days_ago"]

    if len(hist) < max(50 + ma50_ago, 25 + ma25_ago, 60) + 1:
        return None

    current_price = closes.iloc[-1]
    ma5_now, ma5_prev = ma5.iloc[-1], ma5.iloc[-1 - ma5_ago]
    ma25_now, ma25_prev = ma25.iloc[-1], ma25.iloc[-1 - ma25_ago]
    ma50_now, ma50_prev = ma50.iloc[-1], ma50.iloc[-1 - ma50_ago]
    rsi_now, rsi_prev = rsi.iloc[-1], rsi.iloc[-2]

    return_5d = (closes.iloc[-1] / closes.iloc[-6] - 1) * 100 if len(closes) > 5 else None
    return_20d = (closes.iloc[-1] / closes.iloc[-21] - 1) * 100 if len(closes) > 20 else None
    return_60d = (closes.iloc[-1] / closes.iloc[-61] - 1) * 100 if len(closes) > 60 else None

    ma25_deviation = (current_price / ma25_now - 1) * 100 if ma25_now else None

    vol_window_short = cfg["volume_ratio"]["window_short"]
    vol_window_long = cfg["volume_ratio"]["window_long"]
    vol_short_avg = volumes.tail(vol_window_short).mean()
    vol_long_avg = volumes.tail(vol_window_long).mean()
    volume_ratio = vol_short_avg / vol_long_avg if vol_long_avg else None

    high_60d_window = cfg["high_60d"]["lookback_days"]
    high_60d = closes.tail(high_60d_window).max()
    high_60d_ratio = current_price / high_60d if high_60d else None

    prev_close = closes.iloc[-2]
    prev_ma5 = ma5.iloc[-2]
    prev_volume = volumes.iloc[-2]
    current_volume = volumes.iloc[-1]
    prev_vol_short_avg = volumes.iloc[:-1].tail(vol_window_short).mean()
    prev_vol_long_avg = volumes.iloc[:-1].tail(vol_window_long).mean()
    prev_volume_ratio = prev_vol_short_avg / prev_vol_long_avg if prev_vol_long_avg else None

    ma5_breakout = bool(prev_close < prev_ma5 and current_price > ma5_now)
    rsi_reversal = bool(rsi_now > rsi_prev) if pd.notna(rsi_now) and pd.notna(rsi_prev) else False
    volume_reversal = bool(
        prev_volume_ratio is not None
        and prev_volume_ratio <= cfg["volume_ratio"]["good_max"]
        and current_price > prev_close
        and current_volume > prev_volume
    )

    return {
        "date": as_of.strftime("%Y-%m-%d"),
        "close": float(current_price),
        "ma5": float(ma5_now) if pd.notna(ma5_now) else None,
        "ma25": float(ma25_now) if pd.notna(ma25_now) else None,
        "ma50": float(ma50_now) if pd.notna(ma50_now) else None,
        "ma5_prev": float(ma5_prev) if pd.notna(ma5_prev) else None,
        "ma25_prev": float(ma25_prev) if pd.notna(ma25_prev) else None,
        "ma50_prev": float(ma50_prev) if pd.notna(ma50_prev) else None,
        "rsi": float(rsi_now) if pd.notna(rsi_now) else None,
        "rsi_prev": float(rsi_prev) if pd.notna(rsi_prev) else None,
        "return_5d": return_5d,
        "return_20d": return_20d,
        "return_60d": return_60d,
        "ma25_deviation": ma25_deviation,
        "volume_ratio": volume_ratio,
        "high_60d_ratio": high_60d_ratio,
        "ma5_breakout": ma5_breakout,
        "rsi_reversal": rsi_reversal,
        "volume_reversal": volume_reversal,
    }
