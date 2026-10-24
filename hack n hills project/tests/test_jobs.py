"""Real job progress, safe cancellation, bounded state and certificate provenance."""
from pathlib import Path
import threading
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.models import ResearchConfig
from backend.services import orchestration
from backend.services.jobs import InvestigationJobs
from backend.services.ledger import digest


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "data", tmp_path / "evidence")) as client:
        yield client


def wait_for_job(client, key):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        response = client.get(f"/api/investigation-jobs/{key}")
        assert response.status_code == 200, response.text
        job = response.json()
        if job["status"] in {"completed", "cancelled", "failed"}:
            return job
        time.sleep(0.01)
    pytest.fail("Investigation job did not reach a terminal state")


def test_job_completes_real_stages_preserves_certificate_and_reproduces(client):
    response = client.post("/api/investigation-jobs", json={})
    assert response.status_code == 202, response.text
    initial = response.json()
    assert initial["status"] == "queued"
    assert all(stage["status"] == "pending" for stage in initial["stages"])
    job = wait_for_job(client, initial["id"])
    assert job["status"] == "completed", job
    assert job["finished_at"] and job["started_at"] and job["current_stage"] is None
    assert not job["can_cancel"] and job["error"] is None
    assert [stage["id"] for stage in job["stages"]] == [name for name, _ in orchestration.INVESTIGATION_STAGES]
    assert all(stage["status"] in {"completed", "warning"} for stage in job["stages"])
    assert all(stage["started_at"] and stage["finished_at"] for stage in job["stages"])
    assert job["stages"][0]["status"] == "warning"
    curve_stage = next(stage for stage in job["stages"] if stage["id"] == "curves")
    assert curve_stage["status"] == "warning" and "Insufficient curve" in curve_stage["message"]
    certificate = job["result"]
    assert certificate["provenance"] == "IMPORTED UNVERIFIED DATA"
    assert certificate["source_authenticity_verified"] is False
    assert certificate["verdict"] == "INSUFFICIENT EVIDENCE"
    key = job["investigation_id"]
    assert certificate == client.get(f"/api/investigations/{key}").json()
    assert client.post(f"/api/investigations/{key}/reproduce").json()["match"]
    assert client.post(f"/api/investigation-jobs/{job['id']}/cancel").status_code == 200


def test_callbacks_do_not_change_deterministic_stage_outputs(client):
    frame = client.app.state.storage.load()
    config = ResearchConfig().as_dict()
    events = []
    baseline = orchestration.run_stages(frame, config)
    observed = orchestration.run_stages(frame, config, progress=events.append)
    assert digest(observed) == digest(baseline)
    assert len(events) == 16
    for started, finished in zip(events[::2], events[1::2]):
        assert started["status"] == "running"
        assert started["stage"] == finished["stage"]
        assert finished["status"] in {"completed", "warning"}


def test_running_job_is_visible_busy_rejected_and_cancel_stops_before_certificate(client, monkeypatch):
    started, release = threading.Event(), threading.Event()
    original = orchestration.analyze_pair

    def delayed(*args, **kwargs):
        started.set()
        assert release.wait(5), "Test did not release calculation"
        return original(*args, **kwargs)

    monkeypatch.setattr(orchestration, "analyze_pair", delayed)
    key = client.post("/api/investigation-jobs", json={}).json()["id"]
    try:
        assert started.wait(5)
        current = client.get(f"/api/investigation-jobs/{key}").json()
        assert current["status"] == "running" and current["current_stage"] == "mirage"
        assert current["stages"][1]["status"] == "running"
        assert client.get("/health").status_code == 200
        busy = client.post("/api/investigation-jobs", json={})
        assert busy.status_code == 409 and "already running" in busy.json()["detail"]
        cancellation = client.post(f"/api/investigation-jobs/{key}/cancel")
        assert cancellation.status_code == 202
        assert cancellation.json()["status"] == "cancelling"
        assert cancellation.json()["cancel_requested"]
    finally:
        release.set()
    job = wait_for_job(client, key)
    assert job["status"] == "cancelled" and job["result"] is None
    assert all(stage["status"] == "skipped" for stage in job["stages"][2:])
    directory = client.app.state.ledger.directory(job["investigation_id"])
    assert not (directory / "certificate.json").exists()
    assert any(event["stage"] == "cancelled" for event in client.app.state.ledger.events(job["investigation_id"]))


def test_failed_stage_is_visible_and_later_stages_are_skipped(client, monkeypatch):
    def fail(*args, **kwargs):
        raise ValueError("scenario calculation failed")

    monkeypatch.setattr(orchestration, "ghost_market", fail)
    key = client.post("/api/investigation-jobs", json={}).json()["id"]
    job = wait_for_job(client, key)
    assert job["status"] == "failed"
    assert job["error"] == {"type": "ValueError", "message": "scenario calculation failed"}
    stages = {stage["id"]: stage for stage in job["stages"]}
    assert stages["ghost"]["status"] == "failed"
    assert stages["survival"]["status"] == "skipped"
    assert stages["certificate"]["status"] == "skipped"
    assert job["result"] is None
    assert not (client.app.state.ledger.directory(job["investigation_id"]) / "certificate.json").exists()


def test_cancel_is_refused_once_atomic_certificate_commit_begins(client, monkeypatch):
    committing, release = threading.Event(), threading.Event()
    original = Path.replace

    def delay_certificate(path, target):
        if path.name == "certificate.json.tmp":
            committing.set()
            assert release.wait(5), "Test did not release certificate commit"
        return original(path, target)

    monkeypatch.setattr(Path, "replace", delay_certificate)
    key = client.post("/api/investigation-jobs", json={}).json()["id"]
    try:
        assert committing.wait(5)
        current = client.get(f"/api/investigation-jobs/{key}").json()
        assert current["current_stage"] == "certificate" and not current["can_cancel"]
        response = client.post(f"/api/investigation-jobs/{key}/cancel")
        assert response.status_code == 409
        assert "being saved" in response.json()["detail"]
    finally:
        release.set()
    job = wait_for_job(client, key)
    assert job["status"] == "completed" and not job["cancel_requested"]
    assert client.get(f"/api/investigations/{job['investigation_id']}").status_code == 200


def test_job_history_is_bounded_and_snapshots_do_not_expose_mutable_state():
    def runner(storage, ledger, config, **kwargs):
        return {"id": str(uuid.uuid4()), "config": config}

    manager = InvestigationJobs(None, None, runner=runner, max_history=2)
    keys = []
    try:
        for index in range(3):
            job = manager.submit({"seed": index})
            keys.append(job["id"])
            deadline = time.monotonic() + 5
            while manager.get(job["id"])["status"] not in {"completed", "failed"} and time.monotonic() < deadline:
                time.sleep(0.01)
            assert manager.get(job["id"])["status"] == "completed"
        with pytest.raises(FileNotFoundError):
            manager.get(keys[0])
        snapshot = manager.get(keys[-1])
        snapshot["config"]["seed"] = 999
        snapshot["stages"][0]["status"] = "failed"
        assert manager.get(keys[-1])["config"]["seed"] == 2
        assert manager.get(keys[-1])["stages"][0]["status"] == "pending"
    finally:
        manager.shutdown()


def test_job_routes_validate_inputs_and_unknown_identifiers(client):
    assert client.post("/api/investigation-jobs", json={"simulations": 1000000}).status_code == 422
    assert client.get("/api/investigation-jobs/not-a-uuid").status_code == 422
    unknown = str(uuid.uuid4())
    assert client.get(f"/api/investigation-jobs/{unknown}").status_code == 404
    assert client.post(f"/api/investigation-jobs/{unknown}/cancel").status_code == 404


def test_unverified_imports_cannot_receive_positive_final_certificate(client, monkeypatch):
    monkeypatch.setattr(orchestration, "determine_verdict", lambda *args: "SURVIVES MODELED TESTS")
    real = client.post("/api/investigations", json={}).json()
    assert real["verdict"] == "INSUFFICIENT EVIDENCE"
    assert real["provenance"] == "IMPORTED UNVERIFIED DATA"
    synthetic = client.post("/api/investigations", json={"mode": "synthetic"}).json()
    assert synthetic["provenance"] == "SYNTHETIC TEST DATA"


def test_education_route_is_explicitly_hypothetical_and_validates_quotes(client):
    response = client.post("/api/education/compare", json={})
    assert response.status_code == 200, response.text
    assert response.json()["provenance"] == "HYPOTHETICAL EDUCATIONAL EXAMPLE"
    for value in (0, -1, 1e13, "NaN", "Infinity"):
        assert client.post("/api/education/compare", json={"goldm_quote": value}).status_code == 422
