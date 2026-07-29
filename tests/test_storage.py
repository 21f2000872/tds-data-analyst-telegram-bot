from __future__ import annotations

import json

from app.config import Settings
from app.storage import StorageService


def test_local_storage_claim_history_and_public_log(tmp_path) -> None:
    settings = Settings(public_base_url="http://testserver")
    storage = StorageService(settings, local_root=tmp_path)

    assert storage.claim_update(42) is True
    assert storage.claim_update(42) is False
    assert storage.load_history(7) == []

    history = [{"role": "user", "content": "hello"}]
    storage.save_history(7, history)
    assert storage.load_history(7) == history

    url = storage.publish_log( "abc", b'{"event":"ok"}\n')
    assert url == "http://testserver/logs/runs/abc.jsonl"
    saved = tmp_path / "logs" / "runs" / "abc.jsonl"
    assert json.loads(saved.read_text("utf-8")) == {"event": "ok"}

