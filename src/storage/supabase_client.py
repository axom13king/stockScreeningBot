"""Supabase (PostgreSQL) 上のデータへのCRUDラッパー。テーブル定義は db/schema.sql 参照。"""

from datetime import date, datetime

from supabase import Client, create_client

from src.config import settings

_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(settings.supabase_url, settings.supabase_key)
    return _client


# --- holdings ---
# is_test=True は「テストモード」(スクリーニングのTOP10を仮想的に買ったと仮定し、
# 実際の値動きを追う検証用ポジション)。実際の保有(is_test=False)とは
# テーブルを共有しつつ is_test で完全に分離して扱う。

def get_open_holdings(is_test: bool = False) -> list[dict]:
    resp = get_client().table("holdings").select("*").eq("status", "open").eq("is_test", is_test).execute()
    return resp.data


def get_closed_holdings(is_test: bool = False) -> list[dict]:
    resp = get_client().table("holdings").select("*").eq("status", "closed").eq("is_test", is_test).execute()
    return resp.data


def insert_holding(
    ticker_code: str, price: float, quantity: int, ticker_name: str | None = None, is_test: bool = False
) -> None:
    get_client().table("holdings").insert(
        {
            "ticker_code": ticker_code,
            "ticker_name": ticker_name,
            "buy_price": price,
            "buy_date": date.today().isoformat(),
            "quantity": quantity,
            "status": "open",
            "is_test": is_test,
        }
    ).execute()


def close_holding(ticker_code: str, sell_price: float, is_test: bool = False) -> None:
    get_client().table("holdings").update(
        {
            "status": "closed",
            "sell_price": sell_price,
            "sell_date": date.today().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
    ).eq("ticker_code", ticker_code).eq("status", "open").eq("is_test", is_test).execute()


# --- screening history / notification log ---

def insert_screening_history(ticker_code: str, ticker_name: str | None, matched_conditions: list[dict], price: float) -> None:
    get_client().table("screening_history").insert(
        {
            "run_date": date.today().isoformat(),
            "ticker_code": ticker_code,
            "ticker_name": ticker_name,
            "matched_conditions": matched_conditions,
            "price": price,
            "notified_at": datetime.utcnow().isoformat(),
        }
    ).execute()


def insert_notification_log(message: str, channel: str = "telegram", status: str = "sent") -> None:
    get_client().table("notification_log").insert(
        {"channel": channel, "message": message, "status": status}
    ).execute()


# --- telegram polling offset ---

def get_telegram_offset() -> int:
    resp = get_client().table("telegram_poll_state").select("last_update_id").eq("id", 1).single().execute()
    return resp.data["last_update_id"]


def set_telegram_offset(last_update_id: int) -> None:
    get_client().table("telegram_poll_state").update({"last_update_id": last_update_id}).eq("id", 1).execute()
