"""ライブ実行(本日時点)のスイングスクリーニングを組み立てるランナー。

母集団構築・価格取得・ファンダメンタルズ取得・スクリーニング・レポート整形を
一連の流れとしてまとめる。バックテスト(src/backtest/swing_backtest.py)も
同じ build_universe / run_screening を使い回すことで、ロジックの二重実装を避けている。
"""

from datetime import date, timedelta

from src.config import load_swing_config
from src.data.price_cache import bulk_get_fundamentals, bulk_get_price_history
from src.screening.market_risk import evaluate_daily_regime, get_market_snapshot
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

    # 地合いフィルター: 当日のTOPIX下落率・VIXが悪化していれば新規推奨を見送る
    # (個別銘柄のテクニカル指標だけでは市場全体の急落を捉えられないため)
    topix_change_pct = None
    if len(topix_prices) >= 2:
        prev_close = float(topix_prices["Close"].iloc[-2])
        latest_close = float(topix_prices["Close"].iloc[-1])
        if prev_close:
            topix_change_pct = (latest_close - prev_close) / prev_close * 100
    vix_snapshot = get_market_snapshot(cfg).get("vix")

    is_risk_off, regime_reasons = evaluate_daily_regime(topix_change_pct, vix_snapshot, cfg)
    if is_risk_off:
        reason_text = " / ".join(regime_reasons)
        report = (
            f"【スイングスクリーニング {as_of.strftime('%Y-%m-%d')}】\n\n"
            f"⚠️ 本日は地合い悪化のため新規推奨を見送ります。\n{reason_text}"
        )
        return report, []

    candidates = run_screening(universe, price_data, topix_prices, fundamentals, as_of, cfg)
    report = format_report(candidates, as_of.strftime("%Y-%m-%d"))
    return report, candidates
