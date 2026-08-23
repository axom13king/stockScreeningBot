"""必須フィルターとスコアリング(仕様書 セクション14・15)。

各判定の閾値・配点は config/swing_screening.yaml で管理し、コードにハードコードしない。
スコアの細かい傾斜(例: RSIが理想レンジの外側でどれだけ減点するか)は仕様書に
明記されていない部分があり、妥当と考えられる形で実装している。バックテストで調整する前提。
"""

from dataclasses import dataclass, field


@dataclass
class ScoreResult:
    code: str
    passed_required: bool
    failed_filters: list[str]
    score: float
    breakdown: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)


def check_required_filters(metrics: dict, fundamentals: dict, cfg: dict) -> list[str]:
    """必須フィルターのうち満たさなかった項目名のリストを返す(空なら全て合格)。"""
    failed = []
    u = cfg["universe"]

    market_cap = fundamentals.get("market_cap")
    if market_cap is None or market_cap < u["min_market_cap"]:
        failed.append("min_market_cap")

    avg_trading_value = fundamentals.get("avg_trading_value_20d")
    if avg_trading_value is None or avg_trading_value < u["min_avg_trading_value_20d"]:
        failed.append("min_avg_trading_value_20d")

    if not (metrics["ma25"] and metrics["ma50"] and metrics["ma25"] > metrics["ma50"]):
        failed.append("ma25_gt_ma50")

    if not (metrics["ma25"] and metrics["ma25_prev"] and metrics["ma25"] > metrics["ma25_prev"]):
        failed.append("ma25_rising")

    if not (metrics["ma50"] and metrics["ma50_prev"] and metrics["ma50"] > metrics["ma50_prev"]):
        failed.append("ma50_rising")

    if not (metrics["ma5"] and metrics["ma5_prev"] and metrics["ma5"] < metrics["ma5_prev"]):
        failed.append("ma5_falling")

    business_days_to_earnings = fundamentals.get("business_days_to_earnings")
    if business_days_to_earnings is not None and business_days_to_earnings <= cfg["earnings"]["exclude_within_business_days"]:
        failed.append("not_near_earnings")

    return failed


def _tiered(value: float | None, high: float, mid: float, weight: float) -> float:
    if value is None:
        return 0.0
    if value >= high:
        return weight
    if value >= mid:
        return weight * 0.5
    return 0.0


def score_candidate(
    code: str,
    metrics: dict,
    fundamentals: dict,
    sector_ctx: dict,
    market_ctx: dict,
    cfg: dict,
) -> ScoreResult:
    failed = check_required_filters(metrics, fundamentals, cfg)
    weights = cfg["scoring"]["weights"]
    breakdown: dict[str, float] = {}
    reasons: list[str] = []

    if metrics["ma25"] and metrics["ma50"] and metrics["ma25"] > metrics["ma50"]:
        breakdown["ma25_gt_ma50"] = weights["ma25_gt_ma50"]
        reasons.append("25MAが50MAを上回る中期上昇トレンド")

    if metrics["ma25"] and metrics["ma25_prev"] and metrics["ma25"] > metrics["ma25_prev"]:
        breakdown["ma25_rising"] = weights["ma25_rising"]

    if metrics["ma50"] and metrics["ma50_prev"] and metrics["ma50"] > metrics["ma50_prev"]:
        breakdown["ma50_rising"] = weights["ma50_rising"]
        reasons.append("25MA/50MAともに上昇")

    if metrics["close"] and metrics["ma25"] and metrics["close"] > metrics["ma25"]:
        breakdown["price_gt_ma25"] = weights["price_gt_ma25"]

    dev = metrics.get("ma25_deviation")
    dcfg = cfg["deviation"]
    if dev is not None and dcfg["ma25_deviation_min"] <= dev <= dcfg["ma25_deviation_max"]:
        breakdown["ma25_deviation_ok"] = weights["ma25_deviation_ok"]
        reasons.append(f"25MA乖離率{dev:+.1f}%")

    if metrics["ma5"] and metrics["ma5_prev"] and metrics["ma5"] < metrics["ma5_prev"]:
        breakdown["ma5_falling"] = weights["ma5_falling"]

    r5 = metrics.get("return_5d")
    pcfg = cfg["pullback"]
    if r5 is not None and pcfg["return_5d_min"] <= r5 <= pcfg["return_5d_max"]:
        breakdown["return_5d_ok"] = weights["return_5d_ok"]
        reasons.append(f"直近5日で{r5:+.1f}%調整")

    rsi = metrics.get("rsi")
    rcfg = cfg["rsi"]
    if rsi is not None:
        if rcfg["best_min"] <= rsi <= rcfg["best_max"]:
            breakdown["rsi_good"] = weights["rsi_good"]
        elif rcfg["acceptable_min"] <= rsi <= rcfg["acceptable_max"]:
            breakdown["rsi_good"] = weights["rsi_good"] * 0.5
        if rcfg["acceptable_min"] <= rsi <= rcfg["acceptable_max"]:
            reasons.append(f"RSI {rsi:.0f}")

    if sector_ctx.get("is_strong"):
        breakdown["strong_sector"] = weights["strong_sector"]
        reasons.append("所属セクターが20日騰落率上位")

    breakdown["sector_relative_strength"] = _tiered(
        sector_ctx.get("relative_strength"),
        cfg["sector_relative_strength"]["high_threshold"],
        cfg["sector_relative_strength"]["mid_threshold"],
        weights["sector_relative_strength"],
    )
    if sector_ctx.get("relative_strength", 0) and sector_ctx["relative_strength"] > 0:
        reasons.append("セクター平均を上回る相対強度")

    if market_ctx.get("relative_strength") is not None and market_ctx["relative_strength"] > 0:
        breakdown["market_relative_strength"] = weights["market_relative_strength"]
        reasons.append("TOPIXを上回る相対強度")

    vr = metrics.get("volume_ratio")
    vcfg = cfg["volume_ratio"]
    if vr is not None and vcfg["good_min"] <= vr <= vcfg["good_max"]:
        breakdown["volume_decline"] = weights["volume_decline"]
        reasons.append("調整中に出来高減少")

    rebound_weight = weights.get("rebound_signal", 0)
    rebound_score = 0.0
    if metrics.get("ma5_breakout"):
        rebound_score += rebound_weight * 0.4
        reasons.append("本日5MAを回復 → 反発兆候あり")
    if metrics.get("rsi_reversal"):
        rebound_score += rebound_weight * 0.2
    if metrics.get("volume_reversal"):
        rebound_score += rebound_weight * 0.4
        reasons.append("出来高が増加に転じ反発の兆し")
    if rebound_score:
        breakdown["rebound_signal"] = rebound_score

    total_score = sum(breakdown.values())

    return ScoreResult(
        code=code,
        passed_required=not failed,
        failed_filters=failed,
        score=round(total_score, 1),
        breakdown=breakdown,
        reasons=reasons,
    )
