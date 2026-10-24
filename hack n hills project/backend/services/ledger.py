"""Append-only research events and immutable local snapshot artifacts.

Hashes provide reproducibility checks, not cryptographic tamper resistance.
"""
import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from .analytics import clean_json


def canonical(value):
    return json.dumps(clean_json(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class Ledger:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / "ledger.sqlite"
        with self.connect() as con:
            con.execute("CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT, investigation TEXT, timestamp TEXT, stage TEXT, payload TEXT)")

    def connect(self):
        return sqlite3.connect(self.db, timeout=20)

    def directory(self, investigation):
        # UUID parsing prevents reads/writes outside this artifact root.
        key = str(uuid.UUID(investigation))
        return self.root / key

    def append(self, investigation, stage, payload):
        with self.connect() as con:
            con.execute("INSERT INTO events (investigation,timestamp,stage,payload) VALUES (?,?,?,?)", (
                investigation, datetime.now(timezone.utc).isoformat(), stage, canonical(payload)))

    def events(self, investigation):
        with self.connect() as con:
            rows = con.execute("SELECT seq,timestamp,stage,payload FROM events WHERE investigation=? ORDER BY seq", (investigation,)).fetchall()
        return [{"seq": r[0], "timestamp": r[1], "stage": r[2], "payload": json.loads(r[3])} for r in rows]

    def count_similar(self, mode, pair):
        with self.connect() as con:
            rows = con.execute("SELECT payload FROM events WHERE stage='request'").fetchall()
        return sum(json.loads(r[0]).get("mode") == mode and json.loads(r[0]).get("pair") == list(pair) for r in rows)

    def get(self, investigation):
        path = self.directory(investigation) / "certificate.json"
        if not path.exists():
            raise FileNotFoundError("Investigation certificate not found")
        return json.loads(path.read_text(encoding="utf-8"))

    def list(self):
        result = []
        with self.connect() as con:
            ids = con.execute("SELECT investigation,MIN(timestamp) FROM events GROUP BY investigation ORDER BY MIN(timestamp) DESC").fetchall()
        for key, timestamp in ids:
            path = self.directory(key) / "certificate.json"
            if path.exists():
                cert = json.loads(path.read_text(encoding="utf-8"))
                result.append({"id": key, "timestamp": timestamp, "mode": cert["config"]["mode"], "pair": cert["config"]["pair"], "verdict": cert["verdict"], "result_hash": cert["result_hash"]})
            else:
                result.append({"id": key, "timestamp": timestamp, "verdict": "FAILED OR INCOMPLETE", "events": len(self.events(key))})
        return result
