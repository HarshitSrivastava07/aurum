"""Import failures remain isolated, and replay uses complete observed sessions."""
import asyncio
import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app


DAILY_CSV = b"Symbol,Date,Expiry,Close\nGOLDM,2025-01-02,2025-03-05,99000\n"


@pytest.fixture
def app(tmp_path):
    return create_app(tmp_path / "data", tmp_path / "evidence")


def malformed_xml_workbook():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("[Content_Types].xml", "<broken")
    return output.getvalue()


@pytest.mark.parametrize("filename,content", [
    ("broken.xlsx", b"PK\x03\x04broken"),
    ("broken-xml.xlsx", malformed_xml_workbook()),
    ("oversized-field.csv", b"Symbol,Date,Expiry,Close\nGOLDM,2025-01-02,2025-03-05," + b"1" * 200_000),
], ids=["corrupt-xlsx", "malformed-xml", "oversized-csv-field"])
def test_malformed_import_has_report_and_batch_continues(app, filename, content):
    with TestClient(app) as client:
        response = client.post("/api/import", files=[
            ("files", (filename, content)),
            ("files", ("daily.csv", DAILY_CSV)),
        ])
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["reports"][0]["status"] == "rejected"
        assert result["reports"][0]["code"] == "parse_error"
        assert result["reports"][1]["status"] == "accepted"
        assert result["rows_imported"] == 1
        assert client.get("/api/summary").json()["rows"] == 1
        assert len(client.get("/api/imports").json()) == 2


def test_import_processing_does_not_run_on_request_event_loop(app, monkeypatch):
    original = app.state.storage.import_bytes
    observed_event_loops = []

    def record_worker(*args, **kwargs):
        try:
            observed_event_loops.append(asyncio.get_running_loop())
        except RuntimeError:
            observed_event_loops.append(None)
        return original(*args, **kwargs)

    monkeypatch.setattr(app.state.storage, "import_bytes", record_worker)
    with TestClient(app) as client:
        response = client.post("/api/import", files={"files": ("daily.csv", DAILY_CSV)})
    assert response.status_code == 200, response.text
    assert observed_event_loops == [None]


def test_uploads_close_when_processing_raises(app, monkeypatch):
    class Upload:
        filename = "daily.csv"
        closed = False

        async def read(self, size):
            return DAILY_CSV

        async def close(self):
            self.closed = True

    def fail(*args, **kwargs):
        raise RuntimeError("storage unavailable")

    monkeypatch.setattr(app.state.storage, "import_bytes", fail)
    endpoint = next(route.endpoint for route in app.routes if route.path == "/api/import")
    uploads = [Upload(), Upload()]
    with pytest.raises(RuntimeError, match="storage unavailable"):
        asyncio.run(endpoint(files=uploads, requested_date=None, date_order="mdy"))
    assert all(upload.closed for upload in uploads)


def test_sessions_are_sorted_distinct_filtered_and_separate_by_mode(app, monkeypatch):
    storage = app.state.storage
    storage.import_bytes("history.csv", (
        "Symbol,Date,Expiry,Close\n"
        "GOLDM,2025-01-06,2025-03-05,99100\n"
        "GOLDM,2025-01-02,2025-03-05,99000\n"
        "GOLDM,2025-01-02,2025-04-05,99010\n"
        "GOLDTEN,2025-01-03,2025-03-31,99020\n"
    ).encode())
    storage.import_bytes("synthetic.csv", DAILY_CSV.replace(b"2025-01-02", b"2025-01-07"), mode="synthetic")

    def no_full_load(*args, **kwargs):
        raise AssertionError("Session lookup must not load all observations")

    monkeypatch.setattr(storage, "load", no_full_load)
    with TestClient(app) as client:
        assert client.get("/api/sessions").json() == {
            "sessions": ["2025-01-02", "2025-01-03", "2025-01-06"], "total_sessions": 3,
        }
        assert client.get("/api/sessions", params={"symbol": "GOLDM"}).json()["sessions"] == ["2025-01-02", "2025-01-06"]
        assert client.get("/api/sessions", params={"start": "2025-01-03", "end": "2025-01-06"}).json()["sessions"] == ["2025-01-03", "2025-01-06"]
        assert client.get("/api/sessions", params={"mode": "synthetic"}).json()["sessions"] == ["2025-01-07"]
        assert client.get("/api/sessions", params={"symbol": "GOLDPETAL"}).json() == {"sessions": [], "total_sessions": 0}


@pytest.mark.parametrize("params", [
    {"start": "not-a-date"}, {"end": "2025-02-30"},
    {"start": "2025-01-06", "end": "2025-01-02"},
    {"symbol": "UNKNOWN"}, {"mode": "mixed"},
])
def test_sessions_reject_invalid_filters(app, params):
    with TestClient(app) as client:
        assert client.get("/api/sessions", params=params).status_code == 422
