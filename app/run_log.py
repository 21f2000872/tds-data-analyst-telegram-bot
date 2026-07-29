from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class RunLog:
    run_id: str
    events: list[dict[str, Any]] = field(default_factory=list)

    def add(self, event: str, **data: Any) -> None:
        self.events.append({"timestamp": _now(), "event": event, **data})

    def jsonl_bytes(self) -> bytes:
        return (
            "\n".join(
                json.dumps(item, ensure_ascii=False, separators=(",", ":"), default=str)
                for item in self.events
            )
            + "\n"
        ).encode("utf-8")

