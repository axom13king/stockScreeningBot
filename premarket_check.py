"""寄り付き前(東証9:00開場前)の市場リスクチェック。GitHub Actionsから毎朝実行する。

日経225先物・S&P500先物・VIXを見て、前営業日比で大きく崩れていないか確認する。
判定に関わらず毎朝の状況をTelegramに通知し、リスクオフの兆候があれば
保有銘柄一覧とともに警告する(寄り付きでの対応を人間が判断するための材料)。
"""

from src.config import load_swing_config
from src.notify.telegram import send_message
from src.screening.market_risk import evaluate_risk_off, format_snapshot_lines, get_market_snapshot
from src.storage.supabase_client import get_open_holdings


def main() -> None:
    cfg = load_swing_config()
    snapshot = get_market_snapshot(cfg)
    is_risk_off, reasons = evaluate_risk_off(snapshot, cfg)

    lines = ["【寄り付き前チェック】"]
    lines.extend(format_snapshot_lines(snapshot))

    if is_risk_off:
        lines.append("\n⚠️ リスクオフの兆候があります:")
        lines.extend(f"- {r}" for r in reasons)

        holdings = get_open_holdings()
        if holdings:
            lines.append("\n保有銘柄(寄り付きでの対応を検討してください):")
            for h in holdings:
                label = f"{h['ticker_name']}({h['ticker_code']})" if h.get("ticker_name") else h["ticker_code"]
                lines.append(f"- {label}: 購入{h['buy_price']:.0f}円 x{h['quantity']}株")
    else:
        lines.append("\n特に警戒すべき兆候はありません。")

    send_message("\n".join(lines))


if __name__ == "__main__":
    main()
