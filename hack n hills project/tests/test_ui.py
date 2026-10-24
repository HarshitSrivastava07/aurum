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
        if method == "GET" and url.endswith("/api/investigations"):
            return Response({"investigations": []})
        if url.endswith("/api/specifications") or url.endswith("/api/imports"):
            return Response([])
        return Response({"status": "insufficient_evidence", "message": "Test fixture: insufficient historical coverage.", "series": []})

    monkeypatch.setattr(requests, "request", request)
    return calls


def app():
    return AppTest.from_file(APP, default_timeout=15).run()


def button_with_label(at, label):
    return next(button for button in at.button if button.label == label)


def test_all_workspaces_render_and_synthetic_label_survives_navigation(http):
    at = app()
    assert not at.exception
    at.selectbox(key="mode_label").set_value("Synthetic demonstration").run()
    for page in PAGES:
        at.radio(key="page").set_value(page).run()
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
    at.radio(key="page").set_value("Settings").run()
    at.number_input(key="setting_cost_bps").set_value(17.5).run()
    at.number_input(key="setting_seed").set_value(123).run()
    at.radio(key="page").set_value("Ghost Market").run()
    at.button(key="run_Ghost Market").click().run()
    assert not at.exception
    request = [call for call in http if call["method"] == "POST"][-1]
    assert request["url"].endswith("/api/ghost")
    assert request["json"]["cost_bps"] == 17.5
    assert request["json"]["seed"] == 123
    at.radio(key="page").set_value("Settings").run()
    assert at.number_input(key="setting_cost_bps").value == 17.5


def test_replay_advances_one_observed_session_and_preserves_cutoff(http):
    at = app()
    at.radio(key="page").set_value("Time-Locked Replay").run()
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
