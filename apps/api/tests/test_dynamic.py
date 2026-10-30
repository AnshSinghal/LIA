import os

from app.agent import run_dynamic
from app.llm import NO_MODEL_ANSWER


def test_dynamic_path_without_a_model_does_not_invent_a_number(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr("app.agent.provider_order", lambda: [])
    monkeypatch.setattr("app.agent.search", lambda _question: [])
    result = run_dynamic("How many distinct programs appear on the timetable?", "university", 1, None)
    assert result["route"] == "dynamic"
    assert result["answer"] == NO_MODEL_ANSWER
    assert not any(character.isdigit() for character in result["answer"])
    assert result["suggestions"]
    assert os.environ.get("GOOGLE_API_KEY", "") == ""
