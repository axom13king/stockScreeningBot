"""スイングスクリーニングのバックテスト。

「過去のある時点でスクリーナーを実行したら何がTOP10だったか」を再現し、
その後の5/10/20営業日リターンを集計する。ライブ実行(runner.py)と同じ
universe.build_universe() / pipeline.run_screening() を使い回すことで、
スクリーニングロジックとバックテストロジックの二重実装を避けている。

使い方:
    python -m src.backtest.swing_backtest --start 2024-01-01 --end 2026-08-01

閾値を変えて成績を比較する場合は config/swing_screening.yaml を編集するか、
run_backtest() に cfg_override を渡す。
"""

import argparse
import copy
import statistics
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src.config import load_swing_config
from src.data.price_cache import bulk_get_fundamentals, bulk_get_price_history
from src.screening.swing.pipeline import run_screening
from src.screening.swing.universe import build_universe

FORWARD_WINDOWS = (5, 10, 20)  # 営業日後のリターンを計測
# 50MA+20日前比較・60日高値などに必要な事前データを確保するためのバッファ
_LOOKBACK_BUFFER_DAYS = 200


@dataclass
class BacktestStats:
    forward_days: int
    sample_size: int
    win_rate: float | None = None
    avg_return: float | None = None
    median_return: float | None = None
    max_gain: float | None = None
    max_loss: float | None = None
    max_drawdown: float | None = None
    risk_reward: float | None = None


@dataclass
class BacktestResult:
    picks: list[dict] = field(default_factory=list)  # 各TOP10選定の記録(as_of, code, forward returns)
    stats_by_window: dict[int, BacktestStats] = field(default_factory=dict)


def _trading_days(prices_index: pd.DatetimeIndex, as_of: pd.Timestamp) -> pd.DatetimeIndex:
    return prices_index[prices_index <= as_of]


def _forward_return(prices: pd.DataFrame, as_of: pd.Timestamp, n_days: int) -> float | None:
    idx = prices.index
    future_idx = idx[idx > as_of]
    if len(future_idx) < n_days:
        return None
    target_date = future_idx[n_days - 1]
    base_price = prices.loc[as_of, "Close"] if as_of in idx else None
    if base_price is None:
        # as_ofがそのまま存在しない場合(休場日等)は直近の取得可能日を使う
        past_idx = idx[idx <= as_of]
        if past_idx.empty:
            return None
        base_price = prices.loc[past_idx[-1], "Close"]
    future_price = prices.loc[target_date, "Close"]
    return (future_price / base_price - 1) * 100


def _compute_daily_drawdown(picks: list[dict], field: str) -> float | None:
    """日ごとの平均リターン(その日のTOP10を均等配分で持った場合の日次リターン相当)を
    日付順に並べて累積し、最大ドローダウンを計算する。

    個々のpickのリターンをそのまま1本の系列として累積すると、同じ日に選ばれた
    最大10銘柄分が重複して直列に積み上がり意味のない値になるため、
    日付ごとに平均してから1点として扱う。
    """
    daily: dict[str, list[float]] = {}
    for p in picks:
        if p.get(field) is not None:
            daily.setdefault(p["as_of"], []).append(p[field])
    if not daily:
        return None

    dates = sorted(daily.keys())
    daily_returns = [statistics.mean(daily[d]) for d in dates]
    cumulative = np.cumsum(daily_returns)
    running_max = np.maximum.accumulate(cumulative)
    drawdown = cumulative - running_max
    return float(drawdown.min())


def _compute_stats(returns: list[float], forward_days: int, picks: list[dict], field: str) -> BacktestStats:
    if not returns:
        return BacktestStats(forward_days=forward_days, sample_size=0)

    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r <= 0]
    win_rate = len(wins) / len(returns) * 100
    avg_gain = statistics.mean(wins) if wins else 0.0
    avg_loss = statistics.mean(losses) if losses else 0.0
    risk_reward = (avg_gain / abs(avg_loss)) if avg_loss else None

    max_drawdown = _compute_daily_drawdown(picks, field)

    return BacktestStats(
        forward_days=forward_days,
        sample_size=len(returns),
        win_rate=round(win_rate, 1),
        avg_return=round(statistics.mean(returns), 2),
        median_return=round(statistics.median(returns), 2),
        max_gain=round(max(returns), 2),
        max_loss=round(min(returns), 2),
        max_drawdown=round(max_drawdown, 2) if max_drawdown is not None else None,
        risk_reward=round(risk_reward, 2) if risk_reward is not None else None,
    )


def run_backtest(start: str, end: str, cfg_override: dict | None = None) -> BacktestResult:
    cfg = load_swing_config()
    if cfg_override:
        cfg = _deep_merge(cfg, cfg_override)

    universe = build_universe(cfg)
    codes = [u["code"] for u in universe]

    fetch_start = (pd.Timestamp(start) - pd.Timedelta(days=_LOOKBACK_BUFFER_DAYS)).strftime("%Y-%m-%d")
    fetch_end = (pd.Timestamp(end) + pd.Timedelta(days=max(FORWARD_WINDOWS) * 2)).strftime("%Y-%m-%d")

    price_data = bulk_get_price_history(codes, fetch_start, fetch_end)
    topix_code = cfg["market_relative_strength"]["topix_proxy_code"]
    topix_prices = bulk_get_price_history([topix_code], fetch_start, fetch_end)[topix_code]

    # 発行済株式数は現在値を使う(過去時点の正確な値ではない近似。将来的な既知の限界)
    fundamentals = bulk_get_fundamentals(codes)
    for code in fundamentals:
        fundamentals[code] = {k: v for k, v in fundamentals[code].items() if k != "next_earnings_date"}
        # バックテストでは決算日の点在データが手に入らないため、決算除外フィルターは適用しない

    all_dates = sorted(set().union(*[set(df.index) for df in price_data.values() if not df.empty]))
    target_dates = [d for d in all_dates if pd.Timestamp(start) <= d <= pd.Timestamp(end)]

    picks = []
    for as_of in target_dates:
        candidates = run_screening(universe, price_data, topix_prices, fundamentals, as_of, cfg)
        for candidate in candidates:
            code = candidate["code"]
            prices = price_data[code]
            record = {
                "as_of": as_of.strftime("%Y-%m-%d"),
                "code": code,
                "name": candidate["name"],
                "score": candidate["score_result"].score,
            }
            for n in FORWARD_WINDOWS:
                record[f"return_{n}d"] = _forward_return(prices, as_of, n)
            picks.append(record)

    stats_by_window = {}
    for n in FORWARD_WINDOWS:
        field = f"return_{n}d"
        returns = [p[field] for p in picks if p[field] is not None]
        stats_by_window[n] = _compute_stats(returns, n, picks, field)

    return BacktestResult(picks=picks, stats_by_window=stats_by_window)


def _deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    args = parser.parse_args()

    result = run_backtest(args.start, args.end)
    print(f"総選定回数: {len(result.picks)}")
    for n, stats in result.stats_by_window.items():
        print(f"\n--- {n}営業日後リターン ---")
        print(f"サンプル数: {stats.sample_size}")
        if stats.sample_size:
            print(f"勝率: {stats.win_rate}%")
            print(f"平均リターン: {stats.avg_return}%")
            print(f"中央値リターン: {stats.median_return}%")
            print(f"最大利益: {stats.max_gain}%")
            print(f"最大損失: {stats.max_loss}%")
            print(f"最大ドローダウン: {stats.max_drawdown}%")
            print(f"リスクリワード: {stats.risk_reward}")


if __name__ == "__main__":
    main()
