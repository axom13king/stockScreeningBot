"""複数銘柄の日次OHLCVおよびファンダメンタルズをyfinanceから取得し、ローカルにキャッシュする。

スイングスクリーニングは数百銘柄を対象にするため、日々の実行のたびに全期間を再取得すると
Yahoo Finance側のレート制限に引っかかりやすい。そのため価格データは銘柄ごとに保存し、
不足している末尾の日付分だけ差分取得する。
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import yfinance as yf
from yfinance.exceptions import YFRateLimitError

CACHE_ROOT = Path(__file__).resolve().parent.parent.parent / ".cache"
PRICE_CACHE_DIR = CACHE_ROOT / "prices"
FUNDAMENTALS_CACHE_DIR = CACHE_ROOT / "fundamentals"
PRICE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
FUNDAMENTALS_CACHE_DIR.mkdir(parents=True, exist_ok=True)

FUNDAMENTALS_TTL_SECONDS = 7 * 24 * 3600  # 週1回程度の更新で十分(発行済株式数・決算予定日)
_RETRY_DELAYS_SECONDS = [5, 15, 30]  # レート制限時のリトライ間隔


def _to_yf_symbol(code: str) -> str:
    return f"{code}.T"


def _download_with_retry(symbols: list[str], start: str, end: str) -> pd.DataFrame:
    last_error = None
    for delay in [0, *_RETRY_DELAYS_SECONDS]:
        if delay:
            time.sleep(delay)
        try:
            return yf.download(
                symbols, start=start, end=end, group_by="ticker", auto_adjust=False, threads=True, progress=False
            )
        except YFRateLimitError as e:
            last_error = e
    raise last_error


def _price_cache_path(code: str) -> Path:
    return PRICE_CACHE_DIR / f"{code}.parquet"


def bulk_get_price_history(codes: list[str], start: str, end: str, refresh: bool = False) -> dict[str, pd.DataFrame]:
    """指定期間のOHLCVを銘柄ごとに返す。キャッシュがあれば差分のみ取得して更新する。

    戻り値の各DataFrameは列 Open/High/Low/Close/Volume、インデックスはDate。
    """
    result: dict[str, pd.DataFrame] = {}
    cached_by_code: dict[str, pd.DataFrame] = {}
    fetch_groups: dict[str, list[str]] = {}

    for code in codes:
        path = _price_cache_path(code)
        cached = pd.DataFrame()
        if path.exists() and not refresh:
            cached = pd.read_parquet(path)

        if not cached.empty:
            cached_start = cached.index.min().strftime("%Y-%m-%d")
            cached_end = cached.index.max().strftime("%Y-%m-%d")
            if cached_start <= start and cached_end >= end:
                result[code] = cached.loc[start:end]
                continue
            fetch_start = start if cached_start > start else (cached.index.max() + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            fetch_start = start

        cached_by_code[code] = cached
        fetch_groups.setdefault(fetch_start, []).append(code)

    for fetch_start, group_codes in fetch_groups.items():
        if fetch_start > end:
            for code in group_codes:
                result[code] = cached_by_code[code].loc[start:end]
            continue

        symbols = [_to_yf_symbol(c) for c in group_codes]
        raw = _download_with_retry(symbols, fetch_start, end)

        for code in group_codes:
            symbol = _to_yf_symbol(code)
            try:
                df = raw[symbol] if isinstance(raw.columns, pd.MultiIndex) else raw
            except KeyError:
                df = pd.DataFrame()
            df = df.dropna(how="all")
            if not df.empty and df.index.tz is not None:
                df.index = df.index.tz_localize(None)

            existing = cached_by_code[code]
            if not existing.empty:
                combined = pd.concat([existing, df])
                combined = combined[~combined.index.duplicated(keep="last")].sort_index()
            else:
                combined = df

            _price_cache_path(code).parent.mkdir(parents=True, exist_ok=True)
            if not combined.empty:
                combined.to_parquet(_price_cache_path(code))
            result[code] = combined.loc[start:end] if not combined.empty else combined

    return result


def _fundamentals_cache_path(code: str) -> Path:
    return FUNDAMENTALS_CACHE_DIR / f"{code}.json"


def get_fundamentals(code: str, refresh: bool = False) -> dict:
    """発行済株式数・直近決算発表予定日などを取得する(週次キャッシュ)。"""
    path = _fundamentals_cache_path(code)
    if path.exists() and not refresh:
        cached = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - cached["fetched_at"] < FUNDAMENTALS_TTL_SECONDS:
            return cached["data"]

    last_error = None
    info = {}
    next_earnings_date = None
    for delay in [0, *_RETRY_DELAYS_SECONDS]:
        if delay:
            time.sleep(delay)
        try:
            ticker = yf.Ticker(_to_yf_symbol(code))
            info = ticker.info
            try:
                calendar = ticker.calendar
                earnings_dates = calendar.get("Earnings Date") if calendar else None
                if earnings_dates:
                    next_earnings_date = earnings_dates[0].isoformat()
            except Exception:
                next_earnings_date = None
            last_error = None
            break
        except YFRateLimitError as e:
            last_error = e
    if last_error:
        raise last_error

    data = {
        "shares_outstanding": info.get("sharesOutstanding"),
        "market_cap": info.get("marketCap"),
        "next_earnings_date": next_earnings_date,
    }
    path.write_text(json.dumps({"fetched_at": time.time(), "data": data}, ensure_ascii=False), encoding="utf-8")
    return data


def bulk_get_fundamentals(codes: list[str], refresh: bool = False, max_workers: int = 4) -> dict[str, dict]:
    """複数銘柄のファンダメンタルズを並列取得する(.infoは銘柄ごとに個別リクエストのため)。"""
    result: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(get_fundamentals, code, refresh): code for code in codes}
        for future in futures:
            code = futures[future]
            try:
                result[code] = future.result()
            except Exception:
                result[code] = {}
    return result
