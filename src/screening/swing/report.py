"""スイングスクリーニング結果(TOP10)のレポート整形。"""


def format_candidate(rank: int, candidate: dict) -> str:
    m = candidate["metrics"]
    score_result = candidate["score_result"]

    detail = f"{m['close']:.0f}円"
    if m.get("ma25_deviation") is not None:
        detail += f" (25MA乖離{_fmt_pct(m['ma25_deviation'])}"
        detail += f" RSI{m['rsi']:.0f})" if m.get("rsi") is not None else ")"

    lines = [
        f"{rank}位 {candidate['code']} {candidate['name']} スコア{score_result.score}",
        detail,
        "理由: " + " / ".join(score_result.reasons) if score_result.reasons else "",
    ]
    return "\n".join(line for line in lines if line)


def _fmt_pct(value: float | None) -> str:
    return f"{value:+.1f}%" if value is not None else "N/A"


def format_report(candidates: list[dict], as_of: str) -> str:
    if not candidates:
        return f"【スイングスクリーニング {as_of}】\n本日は条件に合致する銘柄がありませんでした。"

    header = f"【スイングスクリーニング TOP{len(candidates)} {as_of}】"
    body = "\n\n".join(format_candidate(i + 1, c) for i, c in enumerate(candidates))
    return f"{header}\n\n{body}"
