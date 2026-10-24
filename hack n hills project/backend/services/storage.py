"""Local DuckDB observations, immutable raw bytes and reproducible Parquet snapshots."""
from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow.parquet as pq

from .ingestion import COLUMNS, NUMERIC, ImportProblem, normalize_table, read_table, sha256, zip_members

_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


class Storage:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir = self.data_dir / "raw"
        self.parquet_dir = self.data_dir / "processed"
        self.raw_dir.mkdir(exist_ok=True)
        self.parquet_dir.mkdir(exist_ok=True)
        self.db_path = self.data_dir / "aurum.duckdb"
        with _LOCKS_GUARD:
            self.lock = _LOCKS.setdefault(str(self.db_path), threading.RLock())
        with self.lock, duckdb.connect(str(self.db_path)) as con:
            fields = ", ".join(f'"{c}" {"DOUBLE" if c in NUMERIC else "VARCHAR"}' for c in COLUMNS)
            con.execute(f"CREATE TABLE IF NOT EXISTS observations ({fields}, PRIMARY KEY (mode,symbol,instrument,date,expiry))")
            con.execute("CREATE TABLE IF NOT EXISTS imports (id VARCHAR PRIMARY KEY, filename VARCHAR, source_hash VARCHAR, mode VARCHAR, timestamp VARCHAR, report VARCHAR)")

    @staticmethod
    def _mode(mode):
        if mode not in {"real", "synthetic"}:
            raise ValueError("mode must be real or synthetic")
        return mode

    def load(self, mode="real", start=None, end=None, symbols=None) -> pd.DataFrame:
        params = [self._mode(mode)]
        where = ["mode = ?"]
        if start:
            where.append("date >= ?")
            params.append(str(start))
        if end:
            where.append("date <= ?")
            params.append(str(end))
        if symbols:
            where.append("symbol IN (" + ",".join("?" for _ in symbols) + ")")
            params.extend(str(s).strip().upper() for s in symbols)
        with self.lock, duckdb.connect(str(self.db_path)) as con:
            return con.execute("SELECT * FROM observations WHERE " + " AND ".join(where) + " ORDER BY date,symbol,expiry", params).df()

    def imports(self, mode=None) -> list[dict]:
        with self.lock, duckdb.connect(str(self.db_path)) as con:
            if mode:
                rows = con.execute("SELECT report FROM imports WHERE mode=? ORDER BY timestamp DESC", [self._mode(mode)]).fetchall()
            else:
                rows = con.execute("SELECT report FROM imports ORDER BY timestamp DESC").fetchall()
        return [json.loads(r[0]) for r in rows]

    def summary(self, mode="real") -> dict:
        frame = self.load(mode)
        imports = self.imports(mode)
        dates = sorted(frame["date"].unique()) if len(frame) else []
        return {"mode": mode, "rows": len(frame), "records": len(frame), "count": len(frame),
                "symbols": sorted(frame["symbol"].unique().tolist()) if len(frame) else [],
                "sessions": len(dates), "start": dates[0] if dates else None, "end": dates[-1] if dates else None,
                "date_range": {"start": dates[0] if dates else None, "end": dates[-1] if dates else None},
                "contracts": int(frame[["symbol", "expiry"]].drop_duplicates().shape[0]),
                "imports": imports, "import_count": len(imports),
                "sources": int(frame["source_hash"].nunique()), "has_real_history": mode == "real" and len(frame) > 0,
                "quality": {"warning_rows": int((frame["validation_status"] == "warning").sum()),
                            "rejected_rows": sum(i.get("rows_rejected", 0) for i in imports)},
                "message": "No daily MCX observations imported." if frame.empty and mode == "real" else ("Synthetic demonstration data; not MCX market history." if mode == "synthetic" else "Imported daily observations; execution and specification checks still apply.")}

    def _save_report(self, report: dict):
        report["id"] = str(uuid.uuid4())
        report["timestamp"] = datetime.now(timezone.utc).isoformat()
        with self.lock, duckdb.connect(str(self.db_path)) as con:
            con.execute("INSERT INTO imports VALUES (?,?,?,?,?,?)", [report["id"], report["filename"], report["source_hash"], report["mode"], report["timestamp"], json.dumps(report, allow_nan=False)])
        return report

    def import_bytes(self, filename, content, requested_date=None, date_order="mdy", mode="real") -> dict:
        self._mode(mode)
        filename = str(filename).replace("\\", "/").split("/")[-1]
        safe_name = re.sub(r"[^A-Za-z0-9._ -]", "_", filename)[:150] or "upload"
        digest = sha256(content)
        raw_path = self.raw_dir / f"{digest}_{safe_name}"
        report = {"filename": filename, "source_hash": digest, "mode": mode,
                  "raw_path": str(raw_path.relative_to(self.data_dir)), "rows_imported": 0,
                  "rows_rejected": 0, "duplicates": 0, "conflicts": 0, "issues": []}
        with self.lock, duckdb.connect(str(self.db_path)) as con:
            previous = con.execute("SELECT id FROM imports WHERE source_hash=? AND mode=? ORDER BY timestamp LIMIT 1", [digest, mode]).fetchone()
        report["duplicate_source"] = bool(previous)
        report["duplicate_of"] = previous[0] if previous else None
        # Do not persist unbounded input even in the raw vault.
        from .ingestion import MAX_BYTES
        if len(content) > MAX_BYTES:
            report.update(status="rejected", error="File exceeds 25 MiB", code="file_size", raw_path=None)
            return self._save_report(report)
        with self.lock:
            if not raw_path.exists():
                raw_path.write_bytes(content)
        try:
            if filename.lower().endswith(".zip"):
                members = zip_members(content)
                children = [self.import_bytes(name, data, requested_date, date_order, mode) for name, data in members]
                report["members"] = children
                for key in ("rows_imported", "rows_rejected", "duplicates", "conflicts"):
                    report[key] = sum(c.get(key, 0) for c in children)
                report["status"] = "accepted" if all(c["status"] in {"accepted", "duplicate"} for c in children) else ("partial" if report["rows_imported"] else "rejected")
                report["format"] = "zip"
                return self._save_report(report)
            table, file_format = read_table(filename, content)
            frame, details = normalize_table(table, filename, content, requested_date, date_order, mode)
            report.update(details, format=file_format)
            # Detect contradictory prices before inserting any row with the same contract identity.
            keys = ["mode", "symbol", "instrument", "date", "expiry"]
            payload = NUMERIC
            inserted = []
            with self.lock, duckdb.connect(str(self.db_path)) as con:
                con.execute("BEGIN TRANSACTION")
                try:
                    for _, group in frame.groupby(keys, dropna=False, sort=False):
                        if len(group[payload].drop_duplicates()) > 1:
                            report["conflicts"] += len(group)
                            report["issues"].append({"severity": "error", "codes": ["conflicting_duplicate_in_file"], "contract": group.iloc[0][keys].tolist()})
                            continue
                        row = group.iloc[0]
                        report["duplicates"] += len(group) - 1
                        existing = con.execute("SELECT " + ",".join(payload) + " FROM observations WHERE mode=? AND symbol=? AND instrument=? AND date=? AND expiry=?", row[keys].tolist()).fetchone()
                        values = [None if pd.isna(row[c]) else row[c] for c in COLUMNS]
                        if existing:
                            new_payload = tuple(None if pd.isna(row[c]) else row[c] for c in payload)
                            if existing == new_payload:
                                report["duplicates"] += 1
                            else:
                                report["conflicts"] += 1
                                report["issues"].append({"severity": "error", "codes": ["conflicting_duplicate_existing"], "contract": row[keys].tolist()})
                            continue
                        con.execute("INSERT INTO observations VALUES (" + ",".join("?" for _ in COLUMNS) + ")", values)
                        inserted.append(values)
                    con.execute("COMMIT")
                except Exception:
                    con.execute("ROLLBACK")
                    raise
                report["rows_imported"] = len(inserted)
                report["rows_rejected"] += report["conflicts"]
                if inserted:
                    parquet = self.parquet_dir / f"{mode}.parquet"
                    temp_path = self.parquet_dir / f"{mode}.{uuid.uuid4().hex}.parquet"
                    try:
                        # Use DuckDB's relation writer: COPY TO parameter binding
                        # order can place the filename before SELECT parameters.
                        pq.write_table(con.execute("SELECT * FROM observations WHERE mode = ?", [mode]).to_arrow_table(), temp_path, compression="zstd")
                        temp_path.replace(parquet)
                        report["parquet"] = str(parquet.relative_to(self.data_dir))
                    except Exception as exc:
                        # DuckDB remains the source of truth if snapshot export is interrupted.
                        report["issues"].append({"severity": "warning", "codes": ["parquet_export_failed"], "detail": str(exc)})
            if report["rows_imported"]:
                report["status"] = "partial" if report["rows_rejected"] else "accepted"
            elif report["duplicates"] and not report["rows_rejected"]:
                report["status"] = "duplicate"
            else:
                report["status"] = "rejected"
                if not report["rows_rejected"]:
                    report["error"] = "No supported daily gold futures rows found"
        except ImportProblem as exc:
            report.update(status="rejected", code=exc.code, error=str(exc), profile=exc.profile)
            report["rows_rejected"] = exc.profile.get("source_rows", 0)
        except (ValueError, OSError, KeyError, ImportError) as exc:
            report.update(status="rejected", code="parse_error", error=f"Could not read file: {exc}")
        return self._save_report(report)

    def contracts(self, mode="real") -> list[dict]:
        from .genome import get_spec, lifecycle
        frame = self.load(mode)
        results = []
        for (symbol, expiry), group in frame.groupby(["symbol", "expiry"]):
            row = group.iloc[-1].to_dict()
            spec = get_spec(symbol, row["date"], expiry, mode=mode)
            # Only compare against sessions observed elsewhere in the uploaded data.
            # Neither weekdays nor absent rows establish an exchange holiday.
            universe = set(frame.loc[(frame["date"] >= group["date"].min()) & (frame["date"] <= group["date"].max()), "date"])
            missing = sorted(universe - set(group["date"]))
            results.append({"symbol": symbol, "expiry": expiry, "contract_id": f"{symbol}:{expiry}",
                            "first_observed": group["date"].min(), "last_observed": group["date"].max(),
                            "sessions": len(group), "latest_close": float(row["close"]),
                            "missing_vs_observed_sessions": missing, "missing_session_count": len(missing),
                            "listing_date": None, "listing_date_status": "not_verified",
                            "spec": spec, "lifecycle": lifecycle(row, spec)})
        return results
