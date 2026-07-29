from __future__ import annotations

import json

import pytest

from app.contracts import parse_agent_answer, telegram_reply


def test_telegram_reply_is_one_exact_json_object() -> None:
    reply = telegram_reply({"value": 391}, "https://example.test/run.jsonl")
    assert reply == (
        '{"answer":{"value":391},'
        '"log_url":"https://example.test/run.jsonl"}'
    )
    assert json.loads(reply) == {
        "answer": {"value": 391},
        "log_url": "https://example.test/run.jsonl",
    }
    assert "```" not in reply


def test_parse_agent_answer_requires_exact_contract() -> None:
    assert parse_agent_answer('{"answer":[1,2]}') == [1, 2]
    with pytest.raises(ValueError):
        parse_agent_answer('{"answer":1,"log_url":"model-must-not-control-this"}')
    with pytest.raises(ValueError):
        parse_agent_answer("not json")

