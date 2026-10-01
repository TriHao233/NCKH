import logging

import pytest

from core.config import settings
from modules.rag import chromadb_engine


def test_http_chroma_client_uses_shared_endpoint_without_logging_token(monkeypatch, caplog):
    calls = []
    client = object()
    monkeypatch.setattr(chromadb_engine, "_chroma_client", None)
    monkeypatch.setattr(settings, "chroma_mode", "http")
    monkeypatch.setattr(settings, "chroma_host", "chroma.internal")
    monkeypatch.setattr(settings, "chroma_port", 8443)
    monkeypatch.setattr(settings, "chroma_ssl", True)
    monkeypatch.setattr(settings, "chroma_auth_token", "test-secret-token")
    monkeypatch.setattr(chromadb_engine.chromadb, "HttpClient",
                        lambda **kwargs: calls.append(kwargs) or client)
    monkeypatch.setattr(chromadb_engine.chromadb, "PersistentClient",
                        lambda **kwargs: pytest.fail("Local Chroma was selected"))

    with caplog.at_level(logging.INFO):
        assert chromadb_engine.get_chroma_client() is client
        assert chromadb_engine.get_chroma_client() is client
    assert len(calls) == 1
    assert {key: calls[0][key] for key in ("host", "port", "ssl", "headers")} == {
        "host": "chroma.internal", "port": 8443, "ssl": True,
        "headers": {"Authorization": "Bearer test-secret-token"},
    }
    assert chromadb_engine.chroma_persist_uri() == "https://chroma.internal:8443"
    assert "test-secret-token" not in caplog.text
    monkeypatch.setattr(chromadb_engine, "_chroma_client", None)


def test_local_chroma_mode_keeps_persistent_client(monkeypatch, tmp_path):
    calls = []
    client = object()
    monkeypatch.setattr(chromadb_engine, "_chroma_client", None)
    monkeypatch.setattr(settings, "chroma_mode", "local")
    monkeypatch.setattr(settings, "chromadb_path", str(tmp_path / "chroma"))
    monkeypatch.setattr(chromadb_engine.chromadb, "PersistentClient",
                        lambda **kwargs: calls.append(kwargs) or client)
    assert chromadb_engine.get_chroma_client() is client
    assert calls[0]["path"] == str((tmp_path / "chroma").resolve())
    assert chromadb_engine.chroma_persist_uri() == calls[0]["path"]
    monkeypatch.setattr(chromadb_engine, "_chroma_client", None)


def test_invalid_chroma_mode_fails_closed(monkeypatch):
    monkeypatch.setattr(chromadb_engine, "_chroma_client", None)
    monkeypatch.setattr(settings, "chroma_mode", "unknown")
    with pytest.raises(ValueError, match="CHROMA_MODE"):
        chromadb_engine.get_chroma_client()
