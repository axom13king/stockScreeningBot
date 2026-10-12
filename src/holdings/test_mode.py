"""テストモード: スクリーニングのTOP10を仮想的に買ったと仮定し、実際の値動き・
既存の売り時ルール(src/holdings/rules.py)でどう転ぶかを継続的に検証する。

バックテストと違い未来の値動きは本当に未知のため、ライブでの検証として
バックテストの前提(スコアリング・売り時ルール)が実運用でも妥当かを確認する目的。
実際の保有(holdings, is_test=False)とは完全に分離して扱う。
"""

from datetime import date, timedelta

import pandas as pd

from src.config import load_swing_config
from src.data.price_cache import bulk_get_price_history
from src.holdings.rules import evaluate_sell_signals
from src.screening.swing.indicators import compute_metrics
from src.storage.supabase_client import close_holding, get_closed_holdings, get_open_holdings, insert_holding

_LOOKBACK_DAYS = 200
_QUANTITY = 1  # 仮想購入のため株数は意味を持たない(%リターンのみで評価)


def _recent_date_range() -> tuple[str, str]:
    today = date.today()
    return (today - timedelta(days=_LOOKBACK_DAYS)).isoformat(), today.isoformat()


def register_test_buys(candidates: list[dict]) -> list[str]:
    """本日のTOP10候補を仮想購入として記録する(既に仮想保有中の銘柄は再購入しない)。"""
    already_open = {h["ticker_code"] for h in get_open_holdings(is_test=True)}
    newly_bought = []
    for candidate in candidates:
        code = candidate["code"]
        if code in already_open:
            continue
        close_price = candidate.get("metrics", {}).get("close")
        if close_price is None:
            continue
        insert_holding(code, close_price, _QUANTITY, candidate.get("name"), is_test=True)
        newly_bought.append(code)
    return newly_bought


def _cumulative_stats() -> dict | None:
    closed = get_closed_holdings(is_test=True)
    returns = [
        (h["sell_price"] - h["buy_price"]) / h["buy_price"] * 100
        for h in closed
        if h.get("sell_price") is not None and h.get("buy_price")
    ]
    if not returns:
        return None
    return {
        "n": len(returns),
        "win_rate": sum(1 for r in returns if r > 0) / len(returns) * 100,
        "avg_return": sum(returns) / len(returns),
    }


def build_test_mode_report(candidates: list[dict]) -> str:
    """本日のTOP10を仮想購入に反映し、仮想保有中の全銘柄の状況をまとめて返す。
    売り時シグナルが出た銘柄はここで自動的に仮想決済する(手動報告を待たない)。
    """
    newly_bought = register_test_buys(candidates)

    holdings = get_open_holdings(is_test=True)
    if not holdings:
        return ""

    from_date, to_date = _recent_date_range()
    codes = [h["ticker_code"] for h in holdings]
    price_data = bulk_get_price_history(codes, from_date, to_date)
    swing_cfg = load_swing_config()

    available_dates = [df.index.max() for df in price_data.values() if not df.empty]
    latest_data_date = max(available_dates).strftime("%Y-%m-%d") if available_dates else "不明"

    lines = [f"【テストモード(仮想TOP10検証) 株価時点: {latest_data_date}】"]
    if newly_bought:
        lines.append(f"本日の新規仮想購入: {', '.join(newly_bought)}")

    for holding in holdings:
        code = holding["ticker_code"]
        prices = price_data.get(code)
        if prices is None or prices.empty:
            lines.append(f"{code}: 現在値を取得できませんでした")
            continue

        current_price = float(prices["Close"].iloc[-1])
        pnl_ratio = (current_price - holding["buy_price"]) / holding["buy_price"] * 100
        label = f"{holding['ticker_name']}({code})" if holding.get("ticker_name") else code
        line = f"{label}: {current_price:.0f}円 ({pnl_ratio:+.1f}%) 購入日{holding['buy_date']}"

        metrics = compute_metrics(prices, pd.Timestamp(prices.index[-1]), swing_cfg)
        signals = evaluate_sell_signals(holding, current_price, prices, metrics)
        if signals:
            close_holding(code, current_price, is_test=True)
            reasons = " / ".join(s.reason for s in signals)
            line += f"\n　→ 売り時シグナルのため仮想決済: {reasons}"

        lines.append(line)

    stats = _cumulative_stats()
    if stats:
        lines.append(
            f"【累計(決済済み{stats['n']}件)】勝率{stats['win_rate']:.1f}% 平均リターン{stats['avg_return']:+.2f}%"
        )

    return "\n\n".join(lines)
