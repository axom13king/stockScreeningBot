"""先物・VIXを使った市場全体のリスクオフ判定。

個別銘柄のテクニカル指標では捉えられない「市場全体の急落」を早期に検知するための
補助的な仕組み。日経225先物・S&P500先物は前営業日比の下落率、VIXは絶対水準で判定する。
閾値は仮値であり、運用しながら調整する想定。
"""

import yfinance as yf


def _get_latest_and_change(symbol: str) -> tuple[float, float] | None:
    """(直近値, 前営業日比%) を返す。データ不足なら None。"""
    h = yf.Ticker(symbol).history(period="5d", auto_adjust=True)
    if len(h) < 2:
        return None
    latest = float(h["Close"].iloc[-1])
    previous = float(h["Close"].iloc[-2])
    if previous == 0:
        return None
    pct_change = (latest - previous) / previous * 100
    return latest, pct_change


def get_market_snapshot(cfg: dict) -> dict:
    """先物・VIXの直近値と前営業日比をまとめて取得する。"""
    mr_cfg = cfg["market_risk"]
    snapshot = {}
    for key, symbol in [
        ("nikkei_futures", mr_cfg["nikkei_futures_symbol"]),
        ("sp500_futures", mr_cfg["sp500_futures_symbol"]),
        ("vix", mr_cfg["vix_symbol"]),
    ]:
        result = _get_latest_and_change(symbol)
        snapshot[key] = {"latest": result[0], "change_pct": result[1]} if result else None
    return snapshot


RISK_OFF_MAX_REASONS = 3   # evaluate_risk_off が判定する条件の数(日経先物・S&P先物・VIX)
DAILY_REGIME_MAX_REASONS = 2  # evaluate_daily_regime が判定する条件の数(TOPIX当日騰落率・VIX)


def evaluate_risk_off(snapshot: dict, cfg: dict) -> tuple[bool, list[str]]:
    """リスクオフ条件に該当するか判定し、該当理由のリストを返す。"""
    mr_cfg = cfg["market_risk"]
    reasons = []

    nikkei = snapshot.get("nikkei_futures")
    if nikkei and nikkei["change_pct"] <= mr_cfg["nikkei_futures_drop_threshold"]:
        reasons.append(f"日経225先物 前営業日比{nikkei['change_pct']:+.1f}%")

    sp500 = snapshot.get("sp500_futures")
    if sp500 and sp500["change_pct"] <= mr_cfg["sp500_futures_drop_threshold"]:
        reasons.append(f"S&P500先物 前営業日比{sp500['change_pct']:+.1f}%")

    vix = snapshot.get("vix")
    if vix and vix["latest"] >= mr_cfg["vix_level_threshold"]:
        reasons.append(f"VIX {vix['latest']:.1f}(警戒水準{mr_cfg['vix_level_threshold']:.0f}以上)")

    return bool(reasons), reasons


def evaluate_daily_regime(topix_change_pct: float | None, vix_snapshot: dict | None, cfg: dict) -> tuple[bool, list[str]]:
    """夕方バッチ用: 先物ではなく、当日の実現値(TOPIX騰落率・VIX)で地合い悪化を判定する。"""
    mr_cfg = cfg["market_risk"]
    reasons = []

    if topix_change_pct is not None and topix_change_pct <= mr_cfg["topix_daily_drop_threshold"]:
        reasons.append(f"TOPIX 本日{topix_change_pct:+.1f}%")

    if vix_snapshot and vix_snapshot["latest"] >= mr_cfg["vix_level_threshold"]:
        reasons.append(f"VIX {vix_snapshot['latest']:.1f}(警戒水準{mr_cfg['vix_level_threshold']:.0f}以上)")

    return bool(reasons), reasons


def severity_level(reasons: list[str]) -> str:
    """該当した理由の数から警戒レベルを返す。

    9期間・約4.7年のバックテストで、リスクオフ判定日は平常日と比べ急落(-1%以上)の
    確率が約3.3倍だったが、該当理由が複数重なる日ほど実際の下落幅も大きい傾向があった
    (例: 過去最大級の下落日は軒並み3条件中2〜3個に該当)。理由の数を単純な深刻度の目安にする。
    """
    count = len(reasons)
    if count >= 3:
        return "厳重警戒"
    if count == 2:
        return "警戒"
    if count == 1:
        return "注意"
    return "平常"


def format_snapshot_lines(snapshot: dict) -> list[str]:
    labels = {"nikkei_futures": "日経225先物", "sp500_futures": "S&P500先物", "vix": "VIX"}
    lines = []
    for key, label in labels.items():
        data = snapshot.get(key)
        if data is None:
            lines.append(f"{label}: 取得できませんでした")
        elif key == "vix":
            lines.append(f"{label}: {data['latest']:.1f}")
        else:
            lines.append(f"{label}: {data['latest']:.0f}({data['change_pct']:+.1f}%)")
    return lines
