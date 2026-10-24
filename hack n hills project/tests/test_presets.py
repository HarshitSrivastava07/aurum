"""Portable preset integrity and user-facing save/load behavior."""
from copy import deepcopy
from io import BytesIO
import json

import pytest
from streamlit.testing.v1 import AppTest
import streamlit as st

from frontend.presets import (
    MAX_PRESET_BYTES, MAX_PRESETS, PresetError, make_preset, parse_preset,
    save_preset, serialize_preset, validate_with_api,
)


CONFIG = {
    "pair": ["GOLDM", "GOLDTEN"], "expiry_a": "2026-03-05", "expiry_b": None,
    "start": "2026-01-02", "end": "2026-01-30", "cutoff": "2026-01-29",
    "window": 20, "z_threshold": 2.3, "capital": 10000000.0,
    "max_lots": 100, "min_volume": 10, "min_oi": 10, "holding_days": 5,
    "execution_delay": 1, "exit_delay": 0, "cost_bps": 17.125,
    "slippage_bps": 2.625, "seed": 4294967295, "simulations": 500,
    "volatility_stress": 1.0, "mode": "synthetic", "baseline": "B",
    "cost_schedule": [{"schedule_id": "Audited fees", "effective_from": "2026-01-01",
                       "effective_to": None, "brokerage_per_lot": 12.345,
                       "exchange_bps": 0.76, "regulatory_bps": 0.01,
                       "buy_tax_bps": 0.0, "sell_tax_bps": 1.0,
                       "gst_fraction": 0.18, "extra_per_lot": 3.5}],
}


def test_roundtrip_preserves_all_fields_without_changing_original():
    original = deepcopy(CONFIG)
    preset = make_preset("Gold research \u20b9", original)
    encoded = serialize_preset(preset)
    assert parse_preset(encoded.encode("utf-8")) == preset
    assert preset["config"] == CONFIG
    assert "api_url" not in encoded
    preset["config"]["pair"][0] = "GOLDPETAL"
    preset["config"]["cost_schedule"][0]["brokerage_per_lot"] = 0
    assert original == CONFIG


@pytest.mark.parametrize("payload", [
    [], {}, {"schema_version": 1, "name": "One"},
    {"schema_version": 2, "name": "One", "config": {}},
    {"schema_version": True, "name": "One", "config": {}},
    {"schema_version": 1, "name": " ", "config": {}},
    {"schema_version": 1, "name": 23, "config": {}},
    {"schema_version": 1, "name": "x" * 81, "config": {}},
    {"schema_version": 1, "name": "multi\nline", "config": {}},
    {"schema_version": 1, "name": "One", "config": []},
    {"schema_version": 1, "name": "One", "config": {}, "api_url": "http://example.invalid"},
    {"schema_version": 1, "name": "One", "config": {"api_url": "http://example.invalid"}},
    {"schema_version": 1, "name": "One", "config": {"preferences": {}}},
])
def test_invalid_envelopes_are_rejected(payload):
    with pytest.raises(PresetError):
        parse_preset(json.dumps(payload))


@pytest.mark.parametrize("raw", [
    b"not JSON", b"\xff", b'{"schema_version":1,"name":"One","config":{},"name":"Two"}',
    b'{"schema_version":1,"name":"One","config":{"window":20,"window":5}}',
    b'{"schema_version":1,"name":"One","config":{"capital":NaN}}',
    b'{"schema_version":1,"name":"One","config":{"capital":Infinity}}',
    b'{"schema_version":1,"name":"One","config":{"capital":1e999}}',
])
def test_invalid_or_ambiguous_json_is_rejected(raw):
    with pytest.raises(PresetError):
        parse_preset(raw)


def test_import_and_export_size_limits_count_utf8_bytes():
    too_large = json.dumps({"schema_version": 1, "name": "One", "config": {"note": "\u20b9" * 24000}}, ensure_ascii=False)
    assert len(too_large) < MAX_PRESET_BYTES < len(too_large.encode("utf-8"))
    with pytest.raises(PresetError, match="64 KiB"):
        parse_preset(too_large)
    with pytest.raises(PresetError, match="64 KiB"):
        make_preset("One", {"note": "x" * MAX_PRESET_BYTES})
    exact = serialize_preset(make_preset("One", {})).encode()
    assert parse_preset(exact + b" " * (MAX_PRESET_BYTES - len(exact)))["name"] == "One"


@pytest.mark.parametrize("config", [{"number": float("inf")}, {1: "lost key type"}, {"tuple": (1, 2)}])
def test_export_refuses_values_that_cannot_roundtrip_exactly(config):
    with pytest.raises(PresetError):
        make_preset("One", config)


def test_session_limit_and_explicit_replacement_preserve_saved_values():
    saved = {f"Preset {i}": make_preset(f"Preset {i}", CONFIG) for i in range(MAX_PRESETS)}
    original = deepcopy(saved)
    with pytest.raises(PresetError, match="20 presets"):
        save_preset(saved, make_preset("New", CONFIG))
    replacement = make_preset("Preset 0", {**CONFIG, "cost_bps": 99.25})
    with pytest.raises(PresetError, match="Replace existing preset"):
        save_preset(saved, replacement)
    changed = save_preset(saved, replacement, replace=True)
    assert len(changed) == MAX_PRESETS
    assert changed["Preset 0"]["config"]["cost_bps"] == 99.25
    assert saved == original
    changed["Preset 1"]["config"]["pair"][0] = "GOLDPETAL"
    assert saved == original


def test_backend_validation_posts_original_values_and_keeps_added_defaults():
    calls = []
    def api(method, path, *, body):
        calls.append((method, path, deepcopy(body)))
        return deepcopy(CONFIG)

    partial = {"mode": "synthetic", "cost_bps": CONFIG["cost_bps"],
               "cost_schedule": [{"schedule_id": "Audited fees", "effective_from": "2026-01-01"}]}
    validated = validate_with_api(make_preset("Shared", partial), api)
    assert calls == [("POST", "/api/validate-config", partial)]
    assert validated == make_preset("Shared", CONFIG)


@pytest.mark.parametrize("response", [
    None, [], {}, {"status": "success"},
    {**CONFIG, "cost_bps": 2}, {**CONFIG, "cost_bps": None},
    {**CONFIG, "pair": "GOLDM,GOLDTEN"}, {**CONFIG, "simulations": True},
    {**CONFIG, "cost_schedule": []}, {**CONFIG, "api_url": "http://example.invalid"},
])
def test_invalid_or_lossy_server_reply_is_rejected(response):
    with pytest.raises(PresetError):
        validate_with_api(make_preset("One", CONFIG), lambda *args, **kwargs: response)


def test_wrong_version_cannot_bypass_validation_helper():
    calls = []
    with pytest.raises(PresetError, match="unsupported"):
        validate_with_api({"schema_version": 2, "name": "One", "config": {}}, lambda *args, **kwargs: calls.append(args))
    assert not calls


HARNESS = '''
from copy import deepcopy
import streamlit as st
from frontend.presets import render_presets
DEFAULT_CONFIG = %r
config = st.session_state.setdefault("test_config", deepcopy(DEFAULT_CONFIG))
def api(method, path, *, body):
    st.session_state.setdefault("test_calls", []).append((method, path, deepcopy(body)))
    if st.session_state.get("test_api_unavailable"):
        raise RuntimeError("The research API is unavailable.")
    return {**deepcopy(DEFAULT_CONFIG), **body}
render_presets(config, api)
''' % CONFIG


def test_save_replace_and_offline_load_through_real_controls():
    at = AppTest.from_string(HARNESS, default_timeout=15).run()
    assert not at.exception
    at.text_input(key="research_preset_name").set_value("Research A").run()
    at.button(key="research_preset_save").click().run()
    assert not at.exception
    assert at.session_state["research_presets"]["Research A"]["config"] == CONFIG
    assert len(at.session_state["test_calls"]) == 1
    at.session_state["test_config"] = {**CONFIG, "cost_bps": 34.25}
    at.button(key="research_preset_save").click().run()
    assert any("already exists" in error.value for error in at.error)
    assert len(at.session_state["test_calls"]) == 1
    assert at.session_state["research_presets"]["Research A"]["config"]["cost_bps"] == CONFIG["cost_bps"]
    at.checkbox(key="research_preset_replace").check().run()
    at.button(key="research_preset_save").click().run()
    assert at.session_state["research_presets"]["Research A"]["config"]["cost_bps"] == 34.25
    at.session_state["test_api_unavailable"] = True
    at.selectbox(key="research_preset_selected").set_value("Research A").run()
    at.button(key="research_preset_load").click().run()
    assert not at.exception
    assert len(at.session_state["test_calls"]) == 2
    assert at.session_state["pending_research_preset"] == make_preset("Research A", {**CONFIG, "cost_bps": 34.25})


def test_failed_save_does_not_create_or_apply_a_preset():
    at = AppTest.from_string(HARNESS, default_timeout=15).run()
    at.session_state["test_api_unavailable"] = True
    at.text_input(key="research_preset_name").set_value("Research A").run()
    at.button(key="research_preset_save").click().run()
    assert not at.exception
    assert any("research API is unavailable" in error.value for error in at.error)
    assert not at.session_state["research_presets"]
    assert "pending_research_preset" not in at.session_state


def test_delete_saved_preset_clears_selection_without_breaking_controls():
    at = AppTest.from_string(HARNESS, default_timeout=15).run()
    at.session_state["research_presets"] = {"One": make_preset("One", CONFIG)}
    at.run()
    at.selectbox(key="research_preset_selected").set_value("One").run()
    at.button(key="research_preset_delete").click().run()
    assert not at.exception
    assert at.session_state["research_presets"] == {}
    assert at.button(key="research_preset_load").disabled


class Upload(BytesIO):
    @property
    def size(self):
        return len(self.getvalue())


def test_upload_validates_and_applies_every_setting(monkeypatch):
    preset = make_preset("Imported research", {**CONFIG, "capital": 0.125, "min_oi": 50000000})
    upload = Upload(serialize_preset(preset).encode("utf-8"))
    # AppTest has no file-uploader interaction API. Replace only its file input;
    # the real button, validation request and session handoff still execute.
    monkeypatch.setattr(st, "file_uploader", lambda *args, **kwargs: upload)
    at = AppTest.from_string(HARNESS, default_timeout=15).run()
    at.button(key="research_preset_import").click().run()
    assert not at.exception
    assert at.session_state["test_calls"] == [("POST", "/api/validate-config", preset["config"])]
    assert at.session_state["pending_research_preset"] == preset
    assert not at.session_state["research_presets"]


@pytest.mark.parametrize("raw", [b"not JSON", b" " * (MAX_PRESET_BYTES + 1)], ids=["malformed", "oversized"])
def test_invalid_upload_never_reaches_api_or_changes_settings(monkeypatch, raw):
    monkeypatch.setattr(st, "file_uploader", lambda *args, **kwargs: Upload(raw))
    at = AppTest.from_string(HARNESS, default_timeout=15).run()
    at.button(key="research_preset_import").click().run()
    assert not at.exception
    assert at.error
    assert "test_calls" not in at.session_state
    assert "pending_research_preset" not in at.session_state


def test_backend_rejected_upload_never_applies_settings(monkeypatch):
    upload = Upload(serialize_preset(make_preset("Imported research", CONFIG)).encode("utf-8"))
    monkeypatch.setattr(st, "file_uploader", lambda *args, **kwargs: upload)
    at = AppTest.from_string(HARNESS, default_timeout=15).run()
    at.session_state["test_api_unavailable"] = True
    at.button(key="research_preset_import").click().run()
    assert not at.exception
    assert any("research API is unavailable" in error.value for error in at.error)
    assert "pending_research_preset" not in at.session_state
