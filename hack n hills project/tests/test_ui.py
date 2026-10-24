"""UI boundary tests: real controls must submit the selected backend inputs.

HTTP is replaced by a recorded fake only in these tests. Financial engines have
their own independent fixtures; the browser client must never recreate them.
"""
from pathlib import Path

import pytest
import requests
from streamlit.testing.v1 import AppTest


APP = str(Path(__file__).resolve().parents[1] / "frontend" / "app.py")
PAGES = [
    "Command Center", "Relative Value Explorer", "Futures Curve Laboratory",
    "Mirage Investigation", "Ghost Market", "Market Red Team",
    "Time-Locked Replay", "Profit Survival Map", "Anomaly DNA",
    "Contract Genome", "Evidence Center", "Data Management", "Settings",
]


class Response:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status_code = status
        self.ok = status < 400

    def json(self):
        return self.payload


@pytest.fixture
def http(monkeypatch):
    calls = []

    def request(method, url, **kwargs):
        calls.append({"method": method, "url": url, **kwargs})
        if url.endswith("/api/summary"):
            return Response({"row_count": 4, "contracts_count": 2, "date_min": "2026-01-02", "date_max": "2026-01-05"})
        if url.endswith("/api/contracts"):
            return Response({"contracts": [
                {"symbol": "GOLDM", "expiry": "2026-03-05"},
                {"symbol": "GOLDTEN", "expiry": "2026-03-31"},
            ]})
        if url.endswith("/api/data"):
            return Response({"records": [
                {"date": "2026-01-02", "symbol": "GOLDM", "close": 130001},
                {"date": "2026-01-05", "symbol": "GOLDM", "close": 130017},
            ]})
        if url.endswith("/api/sessions"):
            return Response({"sessions": ["2026-01-02", "2026-01-05"], "total_sessions": 2})
        if url.endswith("/api/validate-config"):
            from backend.models import ResearchConfig
            return Response(ResearchConfig.model_validate(kwargs["json"]).as_dict())
        if method == "GET" and url.endswith("/api/investigations"):
            return Response({"investigations": []})
        if url.endswith("/api/specifications") or url.endswith("/api/imports"):
            return Response([])
        return Response({"status": "insufficient_evidence", "message": "Test fixture: insufficient historical coverage.", "series": []})

    monkeypatch.setattr(requests, "request", request)
    return calls


def app():
    at = AppTest.from_file(APP, default_timeout=15)
    at.session_state["experience"] = "Research Mode"
    return at.run()


def button_with_label(at, label):
    return next(button for button in at.button if button.label == label)


def test_all_workspaces_render_and_synthetic_label_survives_navigation(http):
    at = app()
    assert not at.exception
    at.selectbox(key="mode_label").set_value("Synthetic demonstration").run()
    for page in PAGES:
        at.selectbox(key="page").set_value(page).run()
        assert not at.exception, (page, at.exception)
        assert any("SYNTHETIC DEMONSTRATION" in warning.value for warning in at.warning), page
    assert any(call["params"] == {"mode": "synthetic"} for call in http)


def test_investigation_controls_send_exact_expiry_and_parameters(http):
    at = app()
    at.selectbox(key="expiry_a_real_GOLDM").set_value("2026-03-05").run()
    at.selectbox(key="expiry_b_real_GOLDTEN").set_value("2026-03-31").run()
    at.number_input(key="holding_days").set_value(8).run()
    at.button(key="run_Command Center").click().run()
    assert not at.exception
    request = [call for call in http if call["method"] == "POST"][-1]
    assert request["url"].endswith("/api/investigations")
    assert request["json"]["expiry_a"] == "2026-03-05"
    assert request["json"]["expiry_b"] == "2026-03-31"
    assert request["json"]["holding_days"] == 8
    assert request["json"]["mode"] == "real"
    assert request["timeout"] == (5, 120)
    at.number_input(key="holding_days").set_value(9).run()
    assert any("assumptions have changed" in item.value for item in at.info)
    assert len([call for call in http if call["method"] == "POST"]) == 1


def test_settings_persist_across_navigation_and_reach_backend(http):
    at = app()
    at.selectbox(key="page").set_value("Settings").run()
    at.number_input(key="setting_cost_bps").set_value(17.5).run()
    at.number_input(key="setting_seed").set_value(123).run()
    at.selectbox(key="page").set_value("Ghost Market").run()
    at.button(key="run_Ghost Market").click().run()
    assert not at.exception
    request = [call for call in http if call["method"] == "POST"][-1]
    assert request["url"].endswith("/api/ghost")
    assert request["json"]["cost_bps"] == 17.5
    assert request["json"]["seed"] == 123
    at.selectbox(key="page").set_value("Settings").run()
    assert at.number_input(key="setting_cost_bps").value == 17.5


def test_replay_advances_one_observed_session_and_preserves_cutoff(http):
    at = app()
    at.selectbox(key="page").set_value("Time-Locked Replay").run()
    button_with_label(at, "Load available replay sessions").click().run()
    button_with_label(at, "Next session →").click().run()
    first = [call for call in http if call["method"] == "POST"][-1]
    assert first["url"].endswith("/api/replay")
    assert first["json"]["end"] == "2026-01-02"
    assert first["json"]["cutoff"] == "2026-01-02"
    button_with_label(at, "Next session →").click().run()
    last = [call for call in http if call["method"] == "POST"][-1]
    assert last["json"]["cutoff"] == "2026-01-05"
    assert button_with_label(at, "Next session →").disabled
    button_with_label(at, "Reset clock").click().run()
    assert not button_with_label(at, "Next session →").disabled
    assert not at.exception


def test_unavailable_api_displays_actionable_error_without_fake_result(monkeypatch):
    def fail(*args, **kwargs):
        raise requests.exceptions.ConnectionError("test-only network failure")
    monkeypatch.setattr(requests, "request", fail)
    at = app()
    at.button(key="run_Command Center").click().run()
    assert not at.exception
    assert any("research API is unavailable" in item.value for item in at.error)
    assert not at.success


def test_backend_rejection_is_visible_and_does_not_create_certificate(http, monkeypatch):
    original = requests.request
    def reject(method, url, **kwargs):
        if method == "POST":
            return Response({"detail": "No verified lifecycle coverage for this contract."}, status=422)
        return original(method, url, **kwargs)
    monkeypatch.setattr(requests, "request", reject)
    at = app()
    at.button(key="run_Command Center").click().run()
    assert not at.exception
    assert any("No verified lifecycle coverage" in item.value for item in at.error)
    assert "result_Command Center" not in at.session_state


def test_metadata_is_reused_until_explicit_refresh(http):
    at = app()
    at.number_input(key="holding_days").set_value(7).run()
    at.selectbox(key="page").set_value("Ghost Market").run()
    assert len([call for call in http if call["url"].endswith("/api/summary")]) == 1
    at.button(key="refresh_data").click().run()
    assert len([call for call in http if call["url"].endswith("/api/summary")]) == 2
    assert not at.exception


def test_invalid_cutoff_prevents_calculation_but_keeps_management_accessible(http):
    from datetime import date
    at = app()
    at.date_input(key="cutoff_real").set_value(date(2025, 12, 31)).run()
    assert any("cutoff must be on or after" in item.value for item in at.error)
    assert not any(button.key == "run_Command Center" for button in at.button)
    at.selectbox(key="page").set_value("Settings").run()
    assert at.text_input(key="setting_api_url")
    assert not at.exception


def test_failed_rerun_removes_previous_result(http, monkeypatch):
    at = app()
    at.button(key="run_Command Center").click().run()
    assert "result_Command Center" in at.session_state
    original = requests.request
    def fail(method, url, **kwargs):
        if method == "POST":
            raise requests.exceptions.Timeout("test failure")
        return original(method, url, **kwargs)
    monkeypatch.setattr(requests, "request", fail)
    at.button(key="run_Command Center").click().run()
    assert "result_Command Center" not in at.session_state
    assert any("configured timeout" in item.value for item in at.error)
    assert not at.exception


def test_refresh_invalidates_results_and_replay(http):
    at = app()
    at.button(key="run_Command Center").click().run()
    at.selectbox(key="page").set_value("Time-Locked Replay").run()
    button_with_label(at, "Load available replay sessions").click().run()
    assert "replay_state" in at.session_state
    at.button(key="refresh_data").click().run()
    assert "result_Command Center" not in at.session_state
    assert "replay_state" not in at.session_state
    assert not at.exception


def test_saved_preset_restores_expiries_dates_and_assumptions(http):
    at = app()
    at.selectbox(key="expiry_a_real_GOLDM").set_value("2026-03-05").run()
    at.number_input(key="holding_days").set_value(8).run()
    at.text_input(key="research_preset_name").set_value("My research").run()
    at.button(key="research_preset_save").click().run()
    assert not at.exception
    at.number_input(key="holding_days").set_value(3).run()
    at.selectbox(key="mode_label").set_value("Synthetic demonstration").run()
    at.selectbox(key="research_preset_selected").set_value("My research").run()
    at.button(key="research_preset_load").click().run()
    assert not at.exception
    assert at.selectbox(key="mode_label").value == "Real MCX history"
    assert at.selectbox(key="expiry_a_real_GOLDM").value == "2026-03-05"
    assert at.number_input(key="holding_days").value == 8
    at.button(key="run_Command Center").click().run()
    submitted = [call for call in http if call["url"].endswith("/api/investigations") and call["method"] == "POST"][-1]["json"]
    assert submitted["holding_days"] == 8
    assert submitted["expiry_a"] == "2026-03-05"
    assert submitted["start"] == "2026-01-02"


def test_empty_workspace_offers_working_demo_shortcut(http, monkeypatch):
    original = requests.request
    def empty(method, url, **kwargs):
        if url.endswith("/api/summary"):
            return Response({"rows": 0, "contracts": 0})
        return original(method, url, **kwargs)
    monkeypatch.setattr(requests, "request", empty)
    at = app()
    at.button(key="explore_demo").click().run()
    assert at.selectbox(key="mode_label").value == "Synthetic demonstration"
    assert any(button.key == "create_demo" for button in at.button)
    assert not at.exception


def test_survival_presets_save_visible_cost_overrides(http):
    at = app()
    at.selectbox(key="page").set_value("Profit Survival Map").run()
    at.number_input(key="survival_cost").set_value(42.5).run()
    at.number_input(key="survival_slippage").set_value(9.5).run()
    at.text_input(key="research_preset_name").set_value("Higher costs").run()
    at.button(key="research_preset_save").click().run()
    config = at.session_state["research_presets"]["Higher costs"]["config"]
    assert config["cost_bps"] == 42.5
    assert config["slippage_bps"] == 9.5
    assert not at.exception


def test_loading_backend_valid_values_does_not_silently_reset_them(http):
    from backend.models import ResearchConfig
    at = app()
    imported = ResearchConfig(capital=0.001, start="1899-12-30", end="2026-01-05", cutoff="2026-01-05",
                              min_oi=100000000, simulations=50, cost_bps=750, seed=2**32-1).as_dict()
    at.session_state["pending_research_preset"] = {"schema_version": 1, "name": "API values", "config": imported}
    at.run()
    assert not at.exception
    at.button(key="run_Command Center").click().run()
    submitted = [call for call in http if call["method"] == "POST"][-1]["json"]
    for name in ("capital", "start", "end", "cutoff", "min_oi", "simulations", "cost_bps", "seed"):
        assert submitted[name] == imported[name], name
    assert not at.exception


def test_failed_pair_scan_clears_previous_scan(http, monkeypatch):
    original = requests.request
    def scan_reply(method, url, **kwargs):
        if url.endswith("/api/scan"):
            return Response([{"pair": ["GOLDM", "GOLDTEN"], "status": "insufficient_evidence"}])
        return original(method, url, **kwargs)
    monkeypatch.setattr(requests, "request", scan_reply)
    at = app()
    at.selectbox(key="page").set_value("Relative Value Explorer").run()
    at.button(key="scan_pairs").click().run()
    assert "pair_scan" in at.session_state
    def fail(method, url, **kwargs):
        if url.endswith("/api/scan"):
            raise requests.exceptions.Timeout("test failure")
        return original(method, url, **kwargs)
    monkeypatch.setattr(requests, "request", fail)
    at.button(key="scan_pairs").click().run()
    assert "pair_scan" not in at.session_state
    assert not at.exception


def test_connection_change_clears_live_results_and_import_reports(http):
    at = app()
    at.button(key="run_Command Center").click().run()
    at.session_state["last_import_result"] = {"rows_imported": 50}
    at.session_state["last_demo_result"] = {"status": "created"}
    at.selectbox(key="page").set_value("Settings").run()
    at.text_input(key="setting_api_url").set_value("http://127.0.0.1:9000").run()
    at.selectbox(key="page").set_value("Command Center").run()
    assert "result_Command Center" not in at.session_state
    assert "last_import_result" not in at.session_state
    assert "last_demo_result" not in at.session_state
    assert any(call["url"] == "http://127.0.0.1:9000/api/summary" for call in http)
    assert not at.exception
