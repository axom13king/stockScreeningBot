"""寄り付き前(東証9:00開場前)の市場リスクチェック。GitHub Actionsから毎朝実行する。

日経225先物・S&P500先物・VIXを見て、前営業日比で大きく崩れていないか確認する。
判定に関わらず毎朝の状況をTelegramに通知し、リスクオフの兆候があれば
警戒レベル(注意/警戒/厳重警戒)とともに、保有銘柄ごとの市場感応度(ベータ)・
売りルールまでの余力を示す(寄り付きでの対応を人間が判断するための材料。自動売買はしない)。
"""

from datetime import date, timedelta

from src.config import load_swing_config
from src.data.price_cache import bulk_get_price_history
from src.holdings.rules import STOP_LOSS_RATIO, TRAILING_STOP_RATIO
from src.notify.telegram import send_long_message
from src.screening.holding_risk import BETA_HIGH_THRESHOLD, BETA_LOW_THRESHOLD, analyze_holding
from src.screening.market_risk import (
    RISK_OFF_MAX_REASONS,
    evaluate_risk_off,
    format_snapshot_lines,
    get_market_snapshot,
    severity_level,
)
from src.storage.supabase_client import get_open_holdings

_LEVEL_EMOJI = {"注意": "⚠️", "警戒": "🔶", "厳重警戒": "🔴"}
_LOOKBACK_DAYS = 120  # ベータ計算(60営業日)に十分な余裕を持たせる
_CUSHION_WARNING_THRESHOLD = 3.0  # 売りルールまでの残り(pt)がこれ以下なら⚠表示


def _format_holding_block(holding: dict, analysis: dict) -> str:
    label = f"{holding['ticker_name']}({holding['ticker_code']})" if holding.get("ticker_name") else holding["ticker_code"]
    beta_text = f"{analysis['beta']:.2f}({analysis['beta_label']})" if analysis["beta"] is not None else "算出不可"

    block = f"{label}\n損益: {analysis['pnl_pct']:+.1f}%\nベータ: {beta_text}"

    warnings = []
    if analysis["stop_loss_cushion"] <= _CUSHION_WARNING_THRESHOLD:
        warnings.append(f"損切りまで残り{analysis['stop_loss_cushion']:.1f}pt")
    if analysis["trailing_cushion"] is not None and analysis["trailing_cushion"] <= _CUSHION_WARNING_THRESHOLD:
        warnings.append(f"トレーリングストップまで残り{analysis['trailing_cushion']:.1f}pt")
    for w in warnings:
        block += f"\n⚠ {w}"

    return block


def main() -> None:
    cfg = load_swing_config()
    snapshot = get_market_snapshot(cfg)
    is_risk_off, reasons = evaluate_risk_off(snapshot, cfg)
    level = severity_level(reasons)

    header = f"【寄り付き前チェック: {_LEVEL_EMOJI.get(level, '')}{level}】" if is_risk_off else "【寄り付き前チェック】"
    blocks = ["\n".join([header, *format_snapshot_lines(snapshot)])]

    if is_risk_off:
        reason_block = "\n".join([f"該当理由({len(reasons)}/{RISK_OFF_MAX_REASONS}件、多いほど深刻):", *(f"- {r}" for r in reasons)])
        blocks.append(reason_block)
    else:
        blocks.append("特に警戒すべき兆候はありません。")

    holdings = get_open_holdings()
    if holdings:
        today = date.today()
        from_date = (today - timedelta(days=_LOOKBACK_DAYS)).isoformat()
        to_date = today.isoformat()

        codes = [h["ticker_code"] for h in holdings]
        price_data = bulk_get_price_history(codes, from_date, to_date)
        topix_code = cfg["market_relative_strength"]["topix_proxy_code"]
        topix_prices = bulk_get_price_history([topix_code], from_date, to_date)[topix_code]

        legend = (
            "保有銘柄ごとの状況\n"
            f"ベータ基準: {BETA_HIGH_THRESHOLD:.1f}以上=高感応度\n"
            f"　　　　　{BETA_LOW_THRESHOLD:.1f}〜{BETA_HIGH_THRESHOLD:.1f}=標準\n"
            f"　　　　　{BETA_LOW_THRESHOLD:.1f}未満=低感応度\n"
            f"(ベータが高いほど市場の動きに連動しやすい)\n"
            f"損切り{STOP_LOSS_RATIO:.0%}・トレーリングストップ{TRAILING_STOP_RATIO:.0%}まで"
            f"残り{_CUSHION_WARNING_THRESHOLD:.0f}pt以下で⚠表示"
        )
        blocks.append(legend)

        for holding in holdings:
            prices = price_data.get(holding["ticker_code"])
            if prices is None or prices.empty:
                blocks.append(f"{holding['ticker_code']}\n現在値を取得できませんでした")
                continue
            current_price = float(prices["Close"].iloc[-1])
            analysis = analyze_holding(holding, current_price, prices, topix_prices)
            blocks.append(_format_holding_block(holding, analysis))

    send_long_message("\n\n".join(blocks))


if __name__ == "__main__":
    main()
