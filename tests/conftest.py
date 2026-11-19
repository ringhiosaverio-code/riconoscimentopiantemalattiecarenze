import pytest


@pytest.fixture(autouse=True)
def _no_local_quiz_manifest(monkeypatch):
    """I test non devono dipendere dal manifest dei dati locali."""
    monkeypatch.setenv("PLANTCARE_QUIZ_MANIFEST", "/percorso/inesistente/manifest.csv")
