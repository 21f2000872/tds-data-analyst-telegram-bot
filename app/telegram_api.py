from __future__ import annotations

import httpx


class TelegramAPI:
    def __init__(self, token: str, timeout_seconds: float = 20.0) -> None:
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.timeout = timeout_seconds

    def send_message(self, chat_id: int, text: str) -> None:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "disable_web_page_preview": True,
                },
            )
            response.raise_for_status()

