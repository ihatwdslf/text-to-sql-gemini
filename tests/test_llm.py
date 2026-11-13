"""Тести логіки повторів і запасної моделі (без справжніх запитів до Gemini)."""
import pytest
from google.genai import errors

from app import config, llm


class FakeModels:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.used_models = []

    def generate_content(self, model, contents, config):
        self.used_models.append(model)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeResponse:
    def __init__(self, sql):
        self.parsed = llm.SQLAnswer(sql=sql, explanation="ok", chart="none")
        self.text = ""


def overloaded():
    return errors.ServerError(503, {"error": {"code": 503, "message": "high demand",
                                              "status": "UNAVAILABLE"}})


@pytest.fixture
def fake_client(monkeypatch):
    def install(outcomes):
        models = FakeModels(outcomes)
        monkeypatch.setattr(llm, "get_client", lambda: type("C", (), {"models": models})())
        monkeypatch.setattr(llm.time, "sleep", lambda s: None)
        return models
    return install


def test_main_model_answers(fake_client):
    models = fake_client([FakeResponse("SELECT 1")])
    answer, model = llm.generate_sql("schema", "q")
    assert answer.sql == "SELECT 1" and model == config.GEMINI_MODEL


def test_switches_to_fallback_when_overloaded(fake_client):
    models = fake_client([overloaded(), overloaded(), FakeResponse("SELECT 2")])
    answer, model = llm.generate_sql("schema", "q")
    assert model == config.GEMINI_FALLBACK_MODEL
    assert models.used_models == [config.GEMINI_MODEL, config.GEMINI_MODEL,
                                  config.GEMINI_FALLBACK_MODEL]


def test_all_models_down(fake_client):
    fake_client([overloaded()] * 3)
    with pytest.raises(llm.GeminiUnavailableError):
        llm.generate_sql("schema", "q")
