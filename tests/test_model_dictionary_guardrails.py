from __future__ import annotations

import pytest

from crud import model_dictionary as md


def test_find_disabled_models_returns_deduplicated_invalid_names(monkeypatch):
    monkeypatch.setattr(md, "get_enabled_model_names", lambda: ["FR-400G", "FR-500G"])

    invalid = md.find_disabled_models(
        ["FR-400G", " FR-600G ", "FR-600G", "FR-700G(加高)", "", None]
    )

    assert invalid == ["FR-600G", "FR-700G"]


def test_is_model_enabled_uses_latest_dictionary_snapshot(monkeypatch):
    state = {"enabled": ["FR-400G"]}

    monkeypatch.setattr(md, "get_enabled_model_names", lambda: list(state["enabled"]))

    assert md.is_model_enabled("FR-400G") is True
    assert md.is_model_enabled("FR-500G") is False

    state["enabled"] = ["FR-500G"]

    assert md.is_model_enabled("FR-400G") is False
    assert md.is_model_enabled("FR-500G") is True


def test_save_model_dictionary_rejects_empty_rows():
    with pytest.raises(RuntimeError, match="至少保留 1 个机型"):
        md.save_model_dictionary([])
