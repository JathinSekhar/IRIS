import pytest


@pytest.fixture(autouse=True)
def _no_real_model_in_tests(monkeypatch):
    """A developer's backend/.env may enable the Groq reply. Tests must never call the real model; test_companion turns it on with a fake."""
    from app.config import settings
    monkeypatch.setattr(settings, "llm_enabled", False)
