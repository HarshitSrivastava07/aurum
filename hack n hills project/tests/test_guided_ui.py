"""Task-based first-use checks; HTTP fakes test dispatch, not financial outcomes."""
from datetime import date

import requests
from streamlit.testing.v1 import AppTest

from tests.test_ui import APP, Response, http
from frontend.explanations import findings


def guided():
    return AppTest.from_file(APP, default_timeout=20).run()


def enter_wizard(at):
    at.button(key="welcome_Guided Investigation_synthetic").click().run()
    assert at.selectbox(key="experience").value == "Guided Mode"
    return at


def test_first_use_home_has_working_paths_and_discloses_source(http):
    at = guided()
    assert not at.exception
    assert at.selectbox(key="page").value == "Welcome"
    assert any("Understand gold futures" in title.value for title in at.title)
    assert not any(item.key == "z_threshold" for item in at.number_input)
    assert any("IMPORTED UNVERIFIED DATA" in item.value for item in at.caption)
    enter_wizard(at)
    assert at.selectbox(key="mode_label").value == "Synthetic demonstration"
    assert any("SYNTHETIC DEMONSTRATION" in item.value for item in at.warning)
    at.selectbox(key="page").set_value("Welcome").run()
    at.button(key="welcome_Command Center_None").click().run()
    assert at.selectbox(key="experience").value == "Research Mode"
    assert at.number_input(key="z_threshold")
    assert not at.exception


def test_wizard_keeps_exact_contracts_and_blocks_invalid_cutoff(http):
    at = enter_wizard(guided())
    at.button(key="guided_continue").click().run()
    assert at.selectbox(key="guide_input_expiry_synthetic_a_GOLDM").value == "2026-03-05"
    at.button(key="guided_continue").click().run()
    at.date_input(key="guide_input_cutoff_synthetic").set_value(date(2025, 12, 31)).run()
    assert at.button(key="guided_continue").disabled
    assert any("first session must" in error.value for error in at.error)
    at.date_input(key="guide_input_cutoff_synthetic").set_value(date(2026, 1, 5)).run()
    at.button(key="guided_back").click().run()
    assert at.selectbox(key="guide_input_expiry_synthetic_a_GOLDM").value == "2026-03-05"
    assert not at.exception


def test_guided_run_submits_same_config_and_renders_real_stage_status(http, monkeypatch):
    original = requests.request
    jobs = []
    def request(method, url, **kwargs):
        if method == "POST" and url.endswith("/api/investigation-jobs"):
            config = kwargs["json"]
            jobs.append(config)
            return Response({"id": "job-fixture", "status": "queued"}, status=202)
        if method == "GET" and url.endswith("/api/investigation-jobs/job-fixture"):
            return Response({"id": "job-fixture", "status": "completed", "can_cancel": False,
                "stages": [{"id": "snapshot", "label": "Preserve data", "status": "warning", "message": "Synthetic fixture"}],
                "result": {"id": "certificate-fixture", "config": jobs[-1], "verdict": "INSUFFICIENT EVIDENCE",
                           "execution_feasibility": "Unverified", "outputs": {"mirage": {"sessions": 0},
                           "replay": {"metrics": {"trades": 0}}, "red_team": {"summary": {"not-evaluable": 4}}}}})
        return original(method, url, **kwargs)
    monkeypatch.setattr(requests, "request", request)
    at = enter_wizard(guided())
    for _ in range(3):
        at.button(key="guided_continue").click().run()
    at.number_input(key="guide_input_cost").set_value(17.5).run()
    at.button(key="guided_continue").click().run()
    at.button(key="guided_run").click().run()
    assert not at.exception
    assert len(jobs) == 1
    assert jobs[0]["cost_bps"] == 17.5
    assert jobs[0]["expiry_a"] == "2026-03-05"
    assert jobs[0]["expiry_b"] == "2026-03-31"
    assert jobs[0]["mode"] == "synthetic"
    assert "guided_job" not in at.session_state
    assert at.session_state["guided_result"]["id"] == "certificate-fixture"
    assert any("INSUFFICIENT EVIDENCE" in title.value for title in at.subheader)
    assert any(button.key == "guided_download" for button in at.get("download_button"))


def test_guided_inputs_survive_switch_to_full_research(http):
    at = enter_wizard(guided())
    for _ in range(3):
        at.button(key="guided_continue").click().run()
    at.number_input(key="guide_input_cost").set_value(31.0).run()
    at.selectbox(key="experience").set_value("Research Mode").run()
    assert at.selectbox(key="expiry_a_synthetic_GOLDM").value == "2026-03-05"
    at.button(key="run_Command Center").click().run()
    submitted = [item for item in http if item["method"] == "POST"][-1]["json"]
    assert submitted["cost_bps"] == 31
    assert submitted["expiry_a"] == "2026-03-05"
    assert not at.exception


def test_learning_example_dispatch_and_disconnected_recovery(http, monkeypatch):
    at = guided()
    at.selectbox(key="page").set_value("Learn gold futures").run()
    at.number_input(key="education_a").set_value(100000.0)
    at.number_input(key="education_b").set_value(101000.0)
    next(button for button in at.button if button.label == "Compare hypothetical quotations").click().run()
    request = [item for item in http if item["method"] == "POST"][-1]
    assert request["url"].endswith("/api/education/compare")
    assert request["json"] == {"goldm_quote": 100000.0, "goldten_quote": 101000.0}
    def fail(*args, **kwargs):
        raise requests.exceptions.ConnectionError("offline test")
    monkeypatch.setattr(requests, "request", fail)
    next(button for button in at.button if button.label == "Compare hypothetical quotations").click().run()
    assert "education_result" not in at.session_state
    assert any("research API is unavailable" in item.value for item in at.error)
    assert not at.exception


def test_explanation_distinguishes_cost_failure_from_no_trade():
    cert = {"verdict": "REJECTED", "outputs": {"mirage": {"sessions": 40},
             "replay": {"metrics": {"trades": 3, "gross_pnl": 50, "net_pnl": -10}}}}
    assert findings(cert)["destination"] == "Profit Survival Map"
    cert["outputs"]["replay"]["metrics"]["trades"] = 0
    assert findings(cert)["destination"] != "Profit Survival Map"
