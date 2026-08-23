"""Telegram Bot APIラッパー(長期ポーリング方式・常時待受サーバー不要)。"""

import requests

from src.config import settings

_API_BASE = "https://api.telegram.org"


def _url(method: str) -> str:
    return f"{_API_BASE}/bot{settings.telegram_bot_token}/{method}"


def send_message(text: str) -> None:
    resp = requests.post(
        _url("sendMessage"),
        json={"chat_id": settings.telegram_chat_id, "text": text},
        timeout=30,
    )
    resp.raise_for_status()


_MAX_MESSAGE_LENGTH = 3500  # Telegramの上限4096文字に対して余裕を持たせる


def send_long_message(text: str) -> None:
    """4096文字制限を超える可能性のある長文を、候補の区切り(空行)で分割して送信する。"""
    if len(text) <= _MAX_MESSAGE_LENGTH:
        send_message(text)
        return

    chunks: list[str] = []
    current = ""
    for block in text.split("\n\n"):
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) > _MAX_MESSAGE_LENGTH and current:
            chunks.append(current)
            current = block
        else:
            current = candidate
    if current:
        chunks.append(current)

    for chunk in chunks:
        send_message(chunk)


def get_updates(offset: int = 0) -> list[dict]:
    """offset以降(未処理)のメッセージ一覧を取得する。"""
    resp = requests.get(
        _url("getUpdates"),
        params={"offset": offset, "timeout": 0},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("result", [])
