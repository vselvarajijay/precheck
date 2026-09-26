from typing import Any

import pytest

from precheck.core.jev import JevClient
from precheck.core.schema import ChoiceQuestion, NoulQuestion, ScoreQuestion

BASE = "https://jev.test"
URL = f"{BASE}/v1/systemone"
KEY = "fake-jev-key-for-tests-0001"

NOUL = NoulQuestion(type="noul", instructions="Is it risky?")
CHOICE = ChoiceQuestion(type="choice", instructions="Kind?", criteria={"a": "A", "b": "B"})
SCORE = ScoreQuestion(type="score", instructions="Risk?", criteria=["low", "mid", "high"])


def ok_body(answers: dict[str, Any] | None = None, model: str = "jev-1.13.0") -> dict[str, Any]:
    return {
        "model": model,
        "answers": answers or {"q": {"type": "noul", "noul": 0.9}},
        "usage": {"input_tokens": 123, "output_tokens": 7},
    }


class SleepRecorder:
    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


@pytest.fixture
def sleeps() -> SleepRecorder:
    return SleepRecorder()


@pytest.fixture
def client(sleeps: SleepRecorder) -> JevClient:
    return JevClient(KEY, base_url=BASE, deadline_s=5, max_retries=3, sleep=sleeps)
