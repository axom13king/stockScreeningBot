"""日次バッチのエントリポイント(GitHub Actionsから実行する)。

処理の流れ:
  1. Telegramの新着メッセージを取得し、売買報告をSupabaseへ反映(形式が違う場合は案内を返信)
  2. 保有銘柄(未売却分のみ)の現在値・損益率を毎回通知し、売り時ルールに該当すればアラートも添える
  3. スイングスクリーニングを実行し、TOP10候補を通知
  4. 売買報告の使い方を毎回リマインドとして送信
"""

from datetime import date, timedelta

import pandas as pd

from src.config import load_swing_config
from src.data.jquants import JQuantsClient
from src.data.price_cache import bulk_get_price_history
from src.holdings.parser import BuyReport, SellReport, parse_message
from src.holdings.rules import evaluate_sell_signals
from src.notify.telegram import get_updates, send_long_message, send_message
from src.screening.swing.indicators import compute_metrics
from src.screening.swing.runner import run_daily_swing_screening
from src.storage.supabase_client import (
    close_holding,
    get_open_holdings,
    get_telegram_offset,
    insert_holding,
    insert_notification_log,
    insert_screening_history,
    set_telegram_offset,
)


USAGE_GUIDE = (
    "【使い方】\n"
    "購入報告: 買 <証券コード4桁> <購入価格> <株数>\n"
    "  例: 買 7203 2500 100\n"
    "売却報告: 売 <証券コード4桁> <売却価格>\n"
    "  例: 売 7203 2600"
)


def _lookup_ticker_name(jquants: JQuantsClient, ticker_code: str) -> str | None:
    try:
        info = jquants.get_listed_info(code=ticker_code)
        return info[0]["CoName"] if info else None
    except Exception:
        return None


def process_telegram_reports() -> None:
    offset = get_telegram_offset()
    updates = get_updates(offset=offset + 1)
    jquants = JQuantsClient()

    for update in updates:
        message = update.get("message", {})
        text = message.get("text", "").strip()
        report = parse_message(text)

        if isinstance(report, BuyReport):
            ticker_name = _lookup_ticker_name(jquants, report.ticker_code)
            insert_holding(report.ticker_code, report.price, report.quantity, ticker_name)
            label = f"{ticker_name}({report.ticker_code})" if ticker_name else report.ticker_code
            send_message(f"購入を記録しました: {label} @ {report.price}円 x{report.quantity}株")
        elif isinstance(report, SellReport):
            ticker_name = _lookup_ticker_name(jquants, report.ticker_code)
            close_holding(report.ticker_code, report.price)
            label = f"{ticker_name}({report.ticker_code})" if ticker_name else report.ticker_code
            send_message(f"売却を記録しました: {label} @ {report.price}円")
        elif text.startswith("買") or text.startswith("売"):
            # 買/売のつもりだが形式が一致しなかったメッセージには、正しい形式を案内する
            send_message(f"認識できませんでした。正しい形式で送ってください。\n\n{USAGE_GUIDE}")

        set_telegram_offset(update["update_id"])


def send_usage_guide() -> None:
    send_message(USAGE_GUIDE)


# compute_metrics()が要求する最低90営業日分に加え、50MA+20日前比較などの余裕を持たせる
_LOOKBACK_DAYS = 200


def _recent_date_range() -> tuple[str, str]:
    today = date.today()
    return (today - timedelta(days=_LOOKBACK_DAYS)).isoformat(), today.isoformat()


def report_holdings() -> None:
    """保有銘柄(status='open'のみ)の状況を毎回通知する。

    売却報告(process_telegram_reports経由でstatus='closed'になった銘柄)は
    get_open_holdings()の対象から自動的に外れるため、実際に売った銘柄への
    アラートはここで自然に止まる。
    """
    from_date, to_date = _recent_date_range()
    holdings = get_open_holdings()
    if not holdings:
        return

    codes = [h["ticker_code"] for h in holdings]
    price_data = bulk_get_price_history(codes, from_date, to_date)
    swing_cfg = load_swing_config()

    lines = [f"【保有銘柄ステータス {date.today().isoformat()}】"]
    for holding in holdings:
        prices = price_data.get(holding["ticker_code"])
        if prices is None or prices.empty:
            lines.append(f"{holding['ticker_code']}: 現在値を取得できませんでした")
            continue

        current_price = float(prices["Close"].iloc[-1])
        pnl_ratio = (current_price - holding["buy_price"]) / holding["buy_price"] * 100

        label = f"{holding['ticker_name']}({holding['ticker_code']})" if holding.get("ticker_name") else holding["ticker_code"]
        line = (
            f"{label}\n"
            f"現在値: {current_price:.0f}円\n"
            f"購入: {holding['buy_price']:.0f}円 x{holding['quantity']}株\n"
            f"損益: {pnl_ratio:+.1f}%"
        )

        metrics = compute_metrics(prices, pd.Timestamp(prices.index[-1]), swing_cfg)
        signals = evaluate_sell_signals(holding, current_price, prices, metrics)
        for signal in signals:
            line += f"\n⚠【売り時アラート】{signal.reason}"
            insert_notification_log(f"【売り時アラート】{signal.ticker_code}: {signal.reason} (現在値 {current_price}円)")

        lines.append(line)

    send_long_message("\n\n".join(lines))


def run_swing_screening() -> None:
    report, candidates = run_daily_swing_screening()
    send_long_message(report)
    insert_notification_log(report)

    for candidate in candidates:
        result = candidate["score_result"]
        insert_screening_history(
            candidate["code"],
            candidate["name"],
            {"score": result.score, "breakdown": result.breakdown, "reasons": result.reasons},
            candidate["metrics"]["close"],
        )


def main() -> None:
    process_telegram_reports()
    report_holdings()
    run_swing_screening()
    send_usage_guide()


if __name__ == "__main__":
    main()
