import io
from datetime import date
import zipfile

import pandas as pd
import pytest

from backend.services.ingestion import ImportProblem, normalize_table, parse_date, read_table, sha256, zip_members
from backend.services.storage import Storage


HEADER = "Commodity,Instrument,Date,ExpiryDate,Open,High,Low,Close,Vol (Lots),OI (Lots)\n"
LINE = "  GOLDM  ,FUTCOM,04/09/2026,05MAY2026,99000,100000,98000,99500,100,500\n"


def csv_bytes(*lines):
    return (HEADER + "".join(lines or [LINE])).encode()


def normalize(content, **kwargs):
    table, _ = read_table("day.csv", content)
    return normalize_table(table, "day.csv", content, today=date(2026, 10, 9), **kwargs)


def test_requested_dmy_returned_mdy_are_not_relabelled():
    frame, report = normalize(csv_bytes(), requested_date="09/10/2026")
    assert frame.iloc[0]["date"] == "2026-04-09"
    assert frame.iloc[0]["requested_date"] == "2026-10-09"
    assert frame.iloc[0]["returned_date"] == "2026-04-09"
    assert "requested_returned_date_mismatch" in report["issues"][0]["codes"]
    assert frame.iloc[0]["symbol"] == "GOLDM"


def test_date_order_is_explicit_and_invalid_dates_are_not_rescued():
    assert parse_date("04/09/2026", "mdy") == "2026-04-09"
    assert parse_date("04/09/2026", "dmy") == "2026-09-04"
    assert parse_date("04SEP2026") == "2026-09-04"
    with pytest.raises(ValueError):
        parse_date("13/04/2026", "mdy")
    with pytest.raises(ValueError):
        parse_date("02/30/2026", "mdy")


@pytest.mark.parametrize("requested,code", [("10/10/2026", "future_requested_date"), ("31/02/2026", "invalid_requested_date")])
def test_bad_requested_dates_fail(requested, code):
    with pytest.raises(ImportProblem) as exc:
        normalize(csv_bytes(), requested_date=requested)
    assert exc.value.code == code


def test_close_is_never_substituted_for_settlement():
    frame, _ = normalize(csv_bytes())
    assert frame.iloc[0]["close"] == 99500
    assert pd.isna(frame.iloc[0]["settlement"])
    assert frame.iloc[0]["source_hash"] == sha256(csv_bytes())


@pytest.mark.parametrize("line,code", [
    (LINE.replace(",100,500", ",-1,500"), "invalid_volume"),
    (LINE.replace(",100,500", ",100,-5"), "invalid_open_interest"),
    (LINE.replace(",99500,", ",NaN,"), "invalid_close"),
    (LINE.replace(",99500,", ",0,"), "invalid_close"),
    (LINE.replace(",99500,", ",101000,"), "close_outside_range"),
    (LINE.replace("04/09/2026", "10/10/2026"), "future_observation"),
    (LINE.replace("05MAY2026", "05APR2026"), "observation_after_expiry"),
])
def test_invalid_observations_are_quarantined(line, code):
    frame, report = normalize(csv_bytes(line))
    assert frame.empty
    assert report["rows_rejected"] == 1
    assert code in report["issues"][0]["codes"]


def test_html_disguised_as_xls_annual_report_is_rejected():
    data = b'<table><tr><th>Commodity</th><th>Year</th><th>Traded Contract (Lots)</th></tr><tr><td>GOLDM</td><td>2025</td><td>1234</td></tr></table>'
    frame, fmt = read_table("annual.xls", data)
    assert fmt == "html-table"
    with pytest.raises(ImportProblem) as exc:
        normalize_table(frame, "annual.xls", data)
    assert exc.value.code == "annual_aggregate"
    assert exc.value.profile["years"] == ["2025"]


def test_real_html_daily_xls_is_supported():
    header, line = csv_bytes().decode().strip().split("\n")
    html = "<table><tr>" + "".join(f"<th>{c}</th>" for c in header.split(",")) + "</tr><tr>" + "".join(f"<td>{c}</td>" for c in line.split(",")) + "</tr></table>"
    table, kind = read_table("daily.xls", html.encode())
    frame, _ = normalize_table(table, "daily.xls", html.encode())
    assert len(frame) == 1 and kind == "html-table"


def test_xlsx_dates_are_read_as_dates():
    from openpyxl import Workbook
    book = Workbook()
    book.active.append(["Symbol", "Date", "ExpiryDate", "Close"])
    book.active.append(["GOLDTEN", date(2026, 4, 9), date(2026, 4, 30), 99000])
    data = io.BytesIO()
    book.save(data)
    table, kind = read_table("daily.xlsx", data.getvalue())
    frame, _ = normalize_table(table, "daily.xlsx", data.getvalue())
    assert kind == "xlsx" and frame.iloc[0]["date"] == "2026-04-09"


def make_zip(name, content):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, content)
    return buffer.getvalue()


@pytest.mark.parametrize("name,code", [("../escape.csv", "zip_path"), ("C:/escape.csv", "zip_path"), ("nested.zip", "zip_member_type"), ("run.exe", "zip_member_type")])
def test_zip_security(name, code):
    with pytest.raises(ImportProblem) as exc:
        zip_members(make_zip(name, csv_bytes()))
    assert exc.value.code == code


def test_storage_keeps_expiry_identity_provenance_and_parquet(tmp_path):
    storage = Storage(tmp_path)
    data = csv_bytes(LINE, LINE.replace("05MAY2026", "05JUN2026"))
    report = storage.import_bytes("day.csv", data)
    assert report["rows_imported"] == 2
    assert report["status"] == "accepted"
    assert (tmp_path / report["raw_path"]).read_bytes() == data
    assert (tmp_path / "processed" / "real.parquet").exists()
    assert len(storage.load()) == 2
    assert storage.load(mode="synthetic").empty
    assert len(storage.contracts()) == 2
    second = storage.import_bytes("same.csv", data)
    assert second["duplicate_source"] and second["duplicates"] == 2
    assert len(storage.load()) == 2


def test_existing_conflicting_duplicate_cannot_overwrite(tmp_path):
    storage = Storage(tmp_path)
    storage.import_bytes("day.csv", csv_bytes())
    report = storage.import_bytes("changed.csv", csv_bytes(LINE.replace("99500", "99400")))
    assert report["conflicts"] == 1
    assert report["rows_imported"] == 0
    assert storage.load().iloc[0]["close"] == 99500


def test_internal_conflicts_quarantine_all_variants(tmp_path):
    storage = Storage(tmp_path)
    report = storage.import_bytes("contradiction.csv", csv_bytes(LINE, LINE.replace("99500", "99400")))
    assert report["conflicts"] == 2
    assert storage.load().empty


def test_modes_can_never_mix_on_load(tmp_path):
    storage = Storage(tmp_path)
    storage.import_bytes("synthetic.csv", csv_bytes(), mode="synthetic")
    assert storage.load("real").empty
    assert len(storage.load("synthetic")) == 1
    with pytest.raises(ValueError):
        storage.load("all")


def test_zip_batch_preserves_parent_and_children(tmp_path):
    storage = Storage(tmp_path)
    data = make_zip("daily.csv", csv_bytes())
    report = storage.import_bytes("batch.zip", data)
    assert report["status"] == "accepted"
    assert report["rows_imported"] == 1
    assert report["members"][0]["source_hash"] == sha256(csv_bytes())
    assert (tmp_path / report["raw_path"]).read_bytes() == data


def test_unsupported_options_are_not_misrepresented_as_futures():
    frame, report = normalize(csv_bytes(LINE.replace("FUTCOM", "OPTFUT")))
    assert frame.empty and report["rows_skipped"] == 1
