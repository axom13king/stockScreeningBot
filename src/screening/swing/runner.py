"""ライブ実行(本日時点)のスイングスクリーニングを組み立てるランナー。

母集団構築・価格取得・ファンダメンタルズ取得・スクリーニング・レポート整形を
一連の流れとしてまとめる。バックテスト(src/backtest/swing_backtest.py)も
同じ build_universe / run_screening を使い回すことで、ロジックの二重実装を避けている。
"""

from datetime import date, timedelta

from src.config import load_swing_config
from src.data.price_cache import bulk_get_fundamentals, bulk_get_price_history
from src.screening.swing.pipeline import run_screening
from src.screening.swing.report import format_report
from src.screening.swing.universe import build_universe

# 50MA+20日前比較・60日高値・セクター60日騰落率などに十分なバッファを確保
_LOOKBACK_DAYS = 400


def run_daily_swing_screening() -> tuple[str, list[dict]]:
    """Telegram通知用のレポート文字列と、候補の生データ(TOP10)を返す。"""
    cfg = load_swing_config()
    universe = build_universe(cfg)
    codes = [u["code"] for u in universe]

    today = date.today()
    start = (today - timedelta(days=_LOOKBACK_DAYS)).isoformat()
    end = today.isoformat()

    price_data = bulk_get_price_history(codes, start, end)
    topix_code = cfg["market_relative_strength"]["topix_proxy_code"]
    topix_prices = bulk_get_price_history([topix_code], start, end)[topix_code]

    fundamentals = bulk_get_fundamentals(codes)

    available_dates = [df.index.max() for df in price_data.values() if not df.empty]
    if not available_dates:
        return "株価データを取得できませんでした。", []
    as_of = max(available_dates)

    candidates = run_screening(universe, price_data, topix_prices, fundamentals, as_of, cfg)
    report = format_report(candidates, as_of.strftime("%Y-%m-%d"))
    return report, candidates
