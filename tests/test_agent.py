from __future__ import annotations

import json
from types import SimpleNamespace

from app.agent import DataAnalystAgent
from app.config import Settings
from app.run_log import RunLog


class Item(SimpleNamespace):
    def model_dump(self, mode="json"):
        return dict(self.__dict__)


class FakeResponses:
    def __init__(self) -> None:
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        if len(self.requests) == 1:
            return SimpleNamespace(
                id="response-1",
                output=[
                    Item(
                        type="function_call",
                        name="inspect_dataset",
                        arguments=json.dumps({"path": "missing.csv"}),
                        call_id="call-1",
                    )
                ],
                output_text="",
            )
        return SimpleNamespace(
            id="response-2",
            output=[],
            output_text='{"answer":{"status":"handled"}}',
        )


def test_agent_returns_structured_answer_and_feeds_tool_error_back(tmp_path) -> None:
    responses = FakeResponses()
    client = SimpleNamespace(responses=responses)
    agent = DataAnalystAgent(Settings(), client=client)
    log = RunLog("test")

    answer = agent.answer("Inspect it", [], tmp_path, log)

    assert answer == {"status": "handled"}
    assert len(responses.requests) == 2
    second_input = responses.requests[1]["input"]
    tool_outputs = [
        item for item in second_input if item.get("type") == "function_call_output"
    ]
    assert len(tool_outputs) == 1
    assert "error" in json.loads(tool_outputs[0]["output"])
    assert any(event["event"] == "tool_result" for event in log.events)
