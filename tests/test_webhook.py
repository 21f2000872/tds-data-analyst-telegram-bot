from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.storage import StorageService


class FakeAgent:
    def answer(self, question, history, run_dir, log):
        log.add("fake_analysis", question=question)
        return {"value": 391}


class FakeTelegram:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    def send_message(self, chat_id: int, text: str) -> None:
        self.sent.append((chat_id, text))


def test_health_reports_missing_and_ready_configuration(tmp_path) -> None:
    missing = Settings(public_base_url="http://testserver")
    missing_client = TestClient(
        create_app(
            missing,
            StorageService(missing, local_root=tmp_path / "missing"),
            FakeAgent(),
            FakeTelegram(),
        )
    )
    response = missing_client.get("/healthz")
    assert response.status_code == 503
    assert "OPENAI_API_KEY" in response.json()["missing"]

    ready = Settings(
        telegram_bot_token="token",
        telegram_webhook_secret="secret",
        openai_api_key="key",
        log_bucket="public-logs",
        state_bucket="private-state",
        public_base_url="http://testserver",
    )
    ready_client = TestClient(
        create_app(
            ready,
            StorageService(ready, local_root=tmp_path / "ready"),
            FakeAgent(),
            FakeTelegram(),
        )
    )
    response = ready_client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "missing": []}


def test_webhook_auth_exact_reply_log_and_deduplication(tmp_path) -> None:
    settings = Settings(
        telegram_webhook_secret="secret",
        public_base_url="http://testserver",
        max_history_messages=4,
    )
    storage = StorageService(settings, local_root=tmp_path)
    telegram = FakeTelegram()
    client = TestClient(
        create_app(settings, storage, FakeAgent(), telegram)
    )
    update = {
        "update_id": 100,
        "message": {"chat": {"id": 55}, "text": "17 * 23?"},
    }

    assert client.post("/telegram/webhook", json=update).status_code == 403
    response = client.post(
        "/telegram/webhook",
        json=update,
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
    )
    assert response.status_code == 204
    assert len(telegram.sent) == 1
    chat_id, raw = telegram.sent[0]
    assert chat_id == 55
    payload = json.loads(raw)
    assert payload["answer"] == {"value": 391}
    assert payload["log_url"].startswith("http://testserver/logs/runs/")
    assert raw == json.dumps(payload, separators=(",", ":"))

    duplicate = client.post(
        "/telegram/webhook",
        json=update,
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
    )
    assert duplicate.status_code == 204
    assert len(telegram.sent) == 1

    log_response = client.get(payload["log_url"])
    assert log_response.status_code == 200
    events = [json.loads(line) for line in log_response.text.splitlines()]
    assert events[0]["event"] == "run_started"
    assert events[-1]["event"] == "run_completed"


def test_webhook_preserves_multi_turn_history(tmp_path) -> None:
    settings = Settings(
        telegram_webhook_secret="secret",
        public_base_url="http://testserver",
        max_history_messages=4,
    )
    storage = StorageService(settings, local_root=tmp_path)
    telegram = FakeTelegram()
    client = TestClient(create_app(settings, storage, FakeAgent(), telegram))
    headers = {"X-Telegram-Bot-Api-Secret-Token": "secret"}

    for update_id, text in [(1, "first"), (2, "follow up")]:
        response = client.post(
            "/telegram/webhook",
            json={"update_id": update_id, "message": {"chat": {"id": 9}, "text": text}},
            headers=headers,
        )
        assert response.status_code == 204

    history = storage.load_history(9)
    assert [item["content"] for item in history if item["role"] == "user"] == [
        "first",
        "follow up",
    ]
