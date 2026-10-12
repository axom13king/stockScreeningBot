"""J-Quants財務情報(/fins/summary)の取得・キャッシュ。

価格データと異なり無料プランの3ヶ月遅延の対象外だが、銘柄ごとに個別のAPI呼び出しが
必要でレート制限にかかりやすいため、全開示履歴をまとめてキャッシュする。
バックテストでのポイントインタイム参照(未来の開示をまだ知らなかったことにする)の
ために全履歴を保持し、呼び出し側で「as_of時点までの最新開示」を選ばせる設計にしている。
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from src.data.jquants import JQuantsClient

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / ".cache" / "fins_summary"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

FUNDAMENTALS_TTL_SECONDS = 7 * 24 * 3600  # 財務情報は四半期更新のため週1回程度で十分


def _cache_path(code: str) -> Path:
    return CACHE_DIR / f"{code}.json"


def get_statements_cached(client: JQuantsClient, code: str, refresh: bool = False) -> list[dict]:
    path = _cache_path(code)
    if path.exists() and not refresh:
        cached = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - cached["fetched_at"] < FUNDAMENTALS_TTL_SECONDS:
            return cached["data"]

    statements = client.get_statements(code)
    path.write_text(
        json.dumps({"fetched_at": time.time(), "data": statements}, ensure_ascii=False), encoding="utf-8"
    )
    return statements


def bulk_get_statements(codes: list[str], refresh: bool = False, max_workers: int = 3) -> dict[str, list[dict]]:
    """複数銘柄の財務情報履歴を並列取得する(J-Quantsのレート制限を考慮し並列数は控えめ)。"""
    client = JQuantsClient()
    result: dict[str, list[dict]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(get_statements_cached, client, code, refresh): code for code in codes}
        for future in futures:
            code = futures[future]
            try:
                result[code] = future.result()
            except Exception:
                result[code] = []
    return result


def latest_statement_as_of(statements: list[dict], as_of_date: str) -> dict | None:
    """as_of_date時点で既に開示済みだった、最新の財務情報を返す(未来の開示は参照しない)。"""
    candidates = [s for s in statements if s.get("DiscDate") and s["DiscDate"] <= as_of_date]
    if not candidates:
        return None
    return max(candidates, key=lambda s: s["DiscDate"])


def extract_eps_bps_roe(statement: dict | None) -> tuple[float | None, float | None, float | None]:
    """EPS/BPS/ROEを取り出す。連結値が空なら単体値(NCEPS/NCBPS)にフォールバックする。"""
    if statement is None:
        return None, None, None

    def _to_float(value):
        try:
            return float(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None

    eps = _to_float(statement.get("EPS")) or _to_float(statement.get("NCEPS"))
    bps = _to_float(statement.get("BPS")) or _to_float(statement.get("NCBPS"))
    roe = _to_float(statement.get("ROE")) or _to_float(statement.get("NCROE"))
    return eps, bps, roe
