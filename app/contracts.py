from __future__ import annotations

import json
from typing import Any


def parse_agent_answer(raw: str) -> Any:
    """Parse the model result and return only its required `answer` value."""
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("The model did not return valid JSON.") from exc
    if not isinstance(value, dict) or set(value) != {"answer"}:
        raise ValueError("The model result must contain exactly one `answer` field.")
    return value["answer"]


def telegram_reply(answer: Any, log_url: str) -> str:
    """Create the exact assignment response without Markdown or surrounding prose."""
    return json.dumps(
        {"answer": answer, "log_url": log_url},
        ensure_ascii=False,
        separators=(",", ":"),
    )

