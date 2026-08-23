"""スイングスクリーニングの中核パイプライン。

ライブ実行(main.py)とバックテスト(src/backtest/swing_backtest.py)の両方から
共通で呼び出す。「過去のある時点でこのスクリーナーを実行したら何がTOP10だったか」を
再現できるよう、価格データはすべて as_of 時点までの範囲でのみ参照する。
"""

import numpy as np
import pandas as pd

from src.screening.swing.indicators import compute_metrics
from src.screening.swing.market import compute_market_return
from src.screening.swing.scoring import score_candidate
from src.screening.swing.sector import compute_sector_returns, determine_strong_sectors


def _avg_trading_value_20d(prices: pd.DataFrame, as_of: pd.Timestamp) -> float | None:
    hist = prices.loc[:as_of].tail(20)
    if hist.empty:
        return None
    return float((hist["Close"] * hist["Volume"]).mean())


def _business_days_to_earnings(next_earnings_date: str | None, as_of: pd.Timestamp) -> int | None:
    if not next_earnings_date:
        return None
    earnings_date = pd.Timestamp(next_earnings_date)
    if earnings_date < as_of:
        return None
    return int(np.busday_count(as_of.date(), earnings_date.date()))


def run_screening(
    universe: list[dict],
    price_data: dict[str, pd.DataFrame],
    topix_prices: pd.DataFrame,
    fundamentals_by_code: dict[str, dict],
    as_of: pd.Timestamp,
    cfg: dict,
) -> list[dict]:
    universe_by_code = {u["code"]: u for u in universe}

    stock_metrics: dict[str, dict] = {}
    for u in universe:
        code = u["code"]
        prices = price_data.get(code)
        if prices is None or prices.empty:
            continue
        metrics = compute_metrics(prices, as_of, cfg)
        if metrics is None:
            continue
        stock_metrics[code] = metrics

    sector_returns = compute_sector_returns(stock_metrics, universe_by_code)
    strong_sectors = determine_strong_sectors(sector_returns, cfg["sector"]["strong_percentile"])
    market_return_20d = compute_market_return(topix_prices, as_of, cfg["market_relative_strength"]["lookback_days"])

    results = []
    for code, metrics in stock_metrics.items():
        base_fundamentals = dict(fundamentals_by_code.get(code, {}))
        base_fundamentals["avg_trading_value_20d"] = _avg_trading_value_20d(price_data[code], as_of)
        base_fundamentals["business_days_to_earnings"] = _business_days_to_earnings(
            base_fundamentals.get("next_earnings_date"), as_of
        )
        # market_capは基準日時点の株価 x 発行済株式数で近似する
        shares_outstanding = base_fundamentals.get("shares_outstanding")
        if shares_outstanding:
            base_fundamentals["market_cap"] = metrics["close"] * shares_outstanding

        sector_code = universe_by_code[code]["sector_code"]
        s_ret = sector_returns.get(sector_code, {})
        rel_strength = None
        if metrics.get("return_20d") is not None and s_ret.get("return_20d") is not None:
            rel_strength = metrics["return_20d"] - s_ret["return_20d"]
        sector_ctx = {"is_strong": sector_code in strong_sectors, "relative_strength": rel_strength}

        market_rel = None
        if metrics.get("return_20d") is not None and market_return_20d is not None:
            market_rel = metrics["return_20d"] - market_return_20d
        market_ctx = {"relative_strength": market_rel}

        score_result = score_candidate(code, metrics, base_fundamentals, sector_ctx, market_ctx, cfg)
        if not score_result.passed_required:
            continue

        results.append(
            {
                "code": code,
                "name": universe_by_code[code]["name"],
                "sector_name": universe_by_code[code]["sector_name"],
                "metrics": metrics,
                "sector_returns": s_ret,
                "market_return_20d": market_return_20d,
                "score_result": score_result,
            }
        )

    results.sort(key=lambda r: r["score_result"].score, reverse=True)
    return results[: cfg["output"]["top_n"]]
