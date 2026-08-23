"""スイングスクリーニング結果(TOP10)のレポート整形。"""


def format_candidate(rank: int, candidate: dict) -> str:
    m = candidate["metrics"]
    s = candidate["sector_returns"]
    score_result = candidate["score_result"]

    lines = [
        f"{rank}位 {candidate['code']} {candidate['name']}  スコア {score_result.score}",
        f"現在値 {m['close']:.0f}円 / 25MA {m['ma25']:.0f} / 50MA {m['ma50']:.0f} / 5MA {m['ma5']:.0f} / RSI {m['rsi']:.0f}" if m.get("rsi") is not None else "",
        f"騰落率 5日{_fmt_pct(m.get('return_5d'))} 20日{_fmt_pct(m.get('return_20d'))} 60日{_fmt_pct(m.get('return_60d'))}",
        f"25MA乖離率 {_fmt_pct(m.get('ma25_deviation'))}",
        f"セクター: {candidate['sector_name']}(5日{_fmt_pct(s.get('return_5d'))} 20日{_fmt_pct(s.get('return_20d'))} 60日{_fmt_pct(s.get('return_60d'))})",
        f"TOPIX20日騰落率 {_fmt_pct(candidate.get('market_return_20d'))}",
        f"出来高比率(5日/25日) {m.get('volume_ratio'):.2f}" if m.get("volume_ratio") is not None else "",
        "",
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
