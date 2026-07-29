from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, JSONResponse

from .agent import DataAnalystAgent
from .config import Settings, get_settings
from .contracts import telegram_reply
from .run_log import RunLog
from .storage import StorageService
from .telegram_api import TelegramAPI


def create_app(
    settings: Settings | None = None,
    storage_service: StorageService | None = None,
    agent: DataAnalystAgent | None = None,
    telegram: TelegramAPI | None = None,
) -> FastAPI:
    cfg = settings or get_settings()
    storage = storage_service or StorageService(cfg)
    analyst = agent or DataAnalystAgent(cfg)
    telegram_api = telegram or TelegramAPI(cfg.telegram_bot_token)
    app = FastAPI(title="Data Analyst Telegram Bot", version="1.0.0")

    @app.get("/")
    def root() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/healthz")
    def health() -> JSONResponse:
        missing = cfg.missing_runtime_values()
        code = status.HTTP_200_OK if not missing else status.HTTP_503_SERVICE_UNAVAILABLE
        return JSONResponse(
            {"status": "ok" if not missing else "not_ready", "missing": missing},
            status_code=code,
        )

    @app.post("/telegram/webhook", status_code=status.HTTP_204_NO_CONTENT)
    def webhook(
        update: dict[str, Any],
        x_telegram_bot_api_secret_token: str | None = Header(default=None),
    ) -> Response:
        if x_telegram_bot_api_secret_token != cfg.telegram_webhook_secret:
            raise HTTPException(status_code=403, detail="Invalid webhook secret.")

        update_id = update.get("update_id")
        message = update.get("message") or update.get("edited_message")
        if not isinstance(update_id, int) or not isinstance(message, dict):
            return Response(status_code=204)
        text = message.get("text")
        chat_id = (message.get("chat") or {}).get("id")
        if not isinstance(text, str) or not text.strip() or not isinstance(chat_id, int):
            return Response(status_code=204)
        if not storage.claim_update(update_id):
            return Response(status_code=204)

        run_id = uuid.uuid4().hex
        log = RunLog(run_id)
        log.add("run_started", update_id=update_id, question=text)
        history = storage.load_history(chat_id)
        with tempfile.TemporaryDirectory(prefix=f"analyst-{run_id}-") as temp:
            try:
                answer = analyst.answer(text, history, Path(temp), log)
                history.extend(
                    [
                        {"role": "user", "content": text},
                        {
                            "role": "assistant",
                            "content": telegram_reply(answer, "<log_url>"),
                        },
                    ]
                )
                history = history[-cfg.max_history_messages :]
                storage.save_history(chat_id, history)
                log.add("run_completed")
            except Exception as exc:
                answer = {"error": "analysis_failed"}
                log.add("run_failed", error=str(exc), error_type=type(exc).__name__)

        log_url = storage.publish_log(run_id, log.jsonl_bytes())
        telegram_api.send_message(chat_id, telegram_reply(answer, log_url))
        return Response(status_code=204)

    if storage.local_root:
        @app.get("/logs/runs/{run_id}.jsonl", include_in_schema=False)
        def local_log(run_id: str) -> FileResponse:
            path = storage.local_root / "logs" / "runs" / f"{run_id}.jsonl"
            if not path.exists():
                raise HTTPException(status_code=404)
            return FileResponse(path, media_type="application/x-ndjson")

    return app


app = create_app()
