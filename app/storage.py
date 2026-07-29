from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import quote

from google.api_core.exceptions import PreconditionFailed
from google.cloud import storage

from .config import Settings


class StorageService:
    """GCS persistence with a local mode used by tests and local development."""

    def __init__(
        self,
        settings: Settings,
        client: storage.Client | None = None,
        local_root: Path | None = None,
    ) -> None:
        self.settings = settings
        self.local_root = local_root
        self.client = client if local_root is None else None
        self._lock = Lock()
        if self.local_root:
            self.local_root.mkdir(parents=True, exist_ok=True)

    def _gcs(self) -> storage.Client:
        if self.client is None:
            self.client = storage.Client()
        return self.client

    def claim_update(self, update_id: int) -> bool:
        object_name = f"updates/{update_id}.json"
        payload = b'{"claimed":true}'
        if self.local_root:
            path = self.local_root / "state" / object_name
            with self._lock:
                if path.exists():
                    return False
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)
                return True
        blob = self._gcs().bucket(self.settings.state_bucket).blob(object_name)
        try:
            blob.upload_from_string(
                payload,
                content_type="application/json",
                if_generation_match=0,
            )
            return True
        except PreconditionFailed:
            return False

    def load_history(self, chat_id: int) -> list[dict[str, Any]]:
        object_name = f"conversations/{chat_id}.json"
        if self.local_root:
            path = self.local_root / "state" / object_name
            return json.loads(path.read_text("utf-8")) if path.exists() else []
        blob = self._gcs().bucket(self.settings.state_bucket).blob(object_name)
        if not blob.exists():
            return []
        return json.loads(blob.download_as_text(encoding="utf-8"))

    def save_history(self, chat_id: int, history: list[dict[str, Any]]) -> None:
        object_name = f"conversations/{chat_id}.json"
        payload = json.dumps(history, ensure_ascii=False, separators=(",", ":"))
        if self.local_root:
            path = self.local_root / "state" / object_name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(payload, encoding="utf-8")
            return
        self._gcs().bucket(self.settings.state_bucket).blob(object_name).upload_from_string(
            payload,
            content_type="application/json",
        )

    def publish_log(self, run_id: str, content: bytes) -> str:
        object_name = f"runs/{run_id}.jsonl"
        if self.local_root:
            path = self.local_root / "logs" / object_name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            base = self.settings.public_base_url or "http://localhost:8080"
            return f"{base}/logs/{quote(object_name, safe='/')}"
        self._gcs().bucket(self.settings.log_bucket).blob(object_name).upload_from_string(
            content,
            content_type="application/x-ndjson",
            cache_control="no-store",
        )
        encoded_bucket = quote(self.settings.log_bucket, safe="")
        encoded_object = quote(object_name, safe="/")
        return f"https://storage.googleapis.com/{encoded_bucket}/{encoded_object}"

