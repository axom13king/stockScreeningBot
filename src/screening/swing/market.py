"""TOPIXに対する相対強度計算(TOPIX連動ETF 1306.T で代替)。"""

import pandas as pd


def compute_market_return(topix_prices: pd.DataFrame, as_of: pd.Timestamp, lookback_days: int) -> float | None:
    hist = topix_prices.loc[:as_of]
    if len(hist) <= lookback_days:
        return None
    closes = hist["Close"]
    return (closes.iloc[-1] / closes.iloc[-(lookback_days + 1)] - 1) * 100
