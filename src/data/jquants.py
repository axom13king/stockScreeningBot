"""J-Quants API v2 (https://jpx-jquants.com/) の薄いクライアントラッパー。

v2ではv1のリフレッシュトークン/IDトークン方式が廃止され、
ダッシュボード(設定 > APIキー)で発行した固定のAPIキーを
`x-api-key` ヘッダーで送信するだけの方式になっている。
"""

import requests

from src.config import settings

BASE_URL = "https://api.jquants.com/v2"


class JQuantsClient:
    def _headers(self) -> dict:
        return {"x-api-key": settings.jquants_api_key}

    def _get_all(self, path: str, params: dict) -> list[dict]:
        """pagination_keyがある限りページングして全件取得する。"""
        results: list[dict] = []
        params = dict(params)
        while True:
            resp = requests.get(f"{BASE_URL}{path}", headers=self._headers(), params=params, timeout=30)
            resp.raise_for_status()
            body = resp.json()
            results.extend(body.get("data", []))
            pagination_key = body.get("pagination_key")
            if not pagination_key:
                break
            params["pagination_key"] = pagination_key
        return results

    def get_listed_info(self, code: str | None = None) -> list[dict]:
        params = {"code": code} if code else {}
        return self._get_all("/equities/master", params)

    def get_daily_quotes(self, code: str, from_date: str | None = None, to_date: str | None = None) -> list[dict]:
        """日次株価(四本値)を取得する。from_date/to_date は 'YYYY-MM-DD' 形式。

        レスポンスのフィールドは短縮名(Date, Code, O, H, L, C, Vo, AdjC など)。
        """
        params = {"code": code}
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date
        return self._get_all("/equities/bars/daily", params)

    def get_statements(self, code: str) -> list[dict]:
        """財務情報(EPS/BPSなど)を取得する。"""
        return self._get_all("/fins/summary", {"code": code})
