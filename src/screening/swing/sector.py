"""セクター(東証33業種)ごとの騰落率と相対強度の計算。

専用のセクター指数データソースがないため、母集団内の構成銘柄の騰落率を
平均して「セクターリターン」を自前で算出する。
"""

import statistics


def compute_sector_returns(stock_metrics: dict[str, dict], universe_by_code: dict[str, dict]) -> dict[str, dict]:
    """sector_code -> {return_5d, return_20d, return_60d, count} の平均値。"""
    grouped: dict[str, list[dict]] = {}
    for code, metrics in stock_metrics.items():
        sector_code = universe_by_code.get(code, {}).get("sector_code")
        if sector_code is None:
            continue
        grouped.setdefault(sector_code, []).append(metrics)

    sector_returns = {}
    for sector_code, members in grouped.items():
        r5 = [m["return_5d"] for m in members if m.get("return_5d") is not None]
        r20 = [m["return_20d"] for m in members if m.get("return_20d") is not None]
        r60 = [m["return_60d"] for m in members if m.get("return_60d") is not None]
        sector_returns[sector_code] = {
            "return_5d": statistics.mean(r5) if r5 else None,
            "return_20d": statistics.mean(r20) if r20 else None,
            "return_60d": statistics.mean(r60) if r60 else None,
            "count": len(members),
        }
    return sector_returns


def determine_strong_sectors(sector_returns: dict[str, dict], percentile: float) -> set[str]:
    """20日騰落率の上位percentile(例 0.30 = 上位30%)に入るセクターコードの集合。"""
    ranked = sorted(
        (s for s, v in sector_returns.items() if v["return_20d"] is not None),
        key=lambda s: sector_returns[s]["return_20d"],
        reverse=True,
    )
    if not ranked:
        return set()
    cutoff = max(1, round(len(ranked) * percentile))
    return set(ranked[:cutoff])
