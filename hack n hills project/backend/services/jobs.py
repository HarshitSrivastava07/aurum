"""Bounded local investigation jobs with real stage progress and cancellation."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import threading
import uuid

from .orchestration import INVESTIGATION_STAGES, InvestigationCancelled, investigate


TERMINAL_STATES = {"completed", "cancelled", "failed"}


class JobConflict(RuntimeError):
    """The single worker is occupied or the result is being committed."""


def _now():
    return datetime.now(timezone.utc).isoformat()


class InvestigationJobs:
    def __init__(self, storage, ledger, *, runner=None, max_history=10):
        self.storage, self.ledger = storage, ledger
        self.runner = runner or investigate
        self.max_history = max(1, int(max_history))
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="aurum-investigation")
        self._jobs = {}
        self._cancellations = {}
        self._committing = set()
        self._active = None
        self._closed = False

    def submit(self, config):
        with self._lock:
            if self._closed:
                raise JobConflict("The investigation worker is shutting down. Retry after the API restarts.")
            if self._active:
                raise JobConflict("An investigation is already running. Wait for it to finish or cancel it before starting another.")
            while len(self._jobs) >= self.max_history:
                oldest = next(iter(self._jobs))
                del self._jobs[oldest]
                self._cancellations.pop(oldest, None)
                self._committing.discard(oldest)
            key = str(uuid.uuid4())
            job = {
                "id": key, "status": "queued", "config": deepcopy(config),
                "created_at": _now(), "started_at": None, "finished_at": None,
                "current_stage": None, "cancel_requested": False, "can_cancel": True,
                "investigation_id": None, "result": None, "error": None,
                "stages": [{"id": name, "label": label, "status": "pending",
                            "started_at": None, "finished_at": None, "message": ""}
                           for name, label in INVESTIGATION_STAGES],
            }
            self._jobs[key] = job
            self._cancellations[key] = threading.Event()
            self._active = key
            self._executor.submit(self._run, key)
            return deepcopy(job)

    def get(self, key):
        with self._lock:
            if key not in self._jobs:
                raise FileNotFoundError("Investigation job was not found. Job status is retained only until API restart or history eviction.")
            return deepcopy(self._jobs[key])

    def cancel(self, key):
        with self._lock:
            if key not in self._jobs:
                raise FileNotFoundError("Investigation job was not found.")
            job = self._jobs[key]
            if job["status"] in TERMINAL_STATES:
                return deepcopy(job)
            if key in self._committing:
                raise JobConflict("The evidence certificate is being saved. Wait for the completed or failed result; cancellation is no longer available.")
            self._cancellations[key].set()
            job.update(status="cancelling", cancel_requested=True, can_cancel=False)
            return deepcopy(job)

    def _progress(self, key, event):
        with self._lock:
            job = self._jobs[key]
            stage = next(item for item in job["stages"] if item["id"] == event["stage"])
            status = event["status"]
            if status == "running":
                # This lock makes accepting cancellation and entering the final
                # commit mutually exclusive, with no post-cancel success race.
                if self._cancellations[key].is_set():
                    raise InvestigationCancelled("Investigation cancelled before the next stage; no certificate was saved.")
                if event["stage"] == "certificate":
                    self._committing.add(key)
                    job["can_cancel"] = False
                stage["started_at"] = _now()
                job["current_stage"] = event["stage"]
            else:
                stage["finished_at"] = _now()
            stage.update(status=status, message=str(event.get("message", ""))[:2000])
            job["investigation_id"] = event.get("investigation_id") or job["investigation_id"]

    def _run(self, key):
        with self._lock:
            job = self._jobs[key]
            job["started_at"] = _now()
            if not job["cancel_requested"]:
                job["status"] = "running"
            config = deepcopy(job["config"])
            cancellation = self._cancellations[key]
        outcome = "failed"
        result = None
        error = None
        reason = ""
        try:
            if cancellation.is_set():
                raise InvestigationCancelled("Investigation cancelled before processing began.")
            result = self.runner(self.storage, self.ledger, config,
                                 progress=lambda event: self._progress(key, event),
                                 cancel_requested=cancellation.is_set)
            with self._lock:
                if cancellation.is_set() and key not in self._committing:
                    raise InvestigationCancelled("Investigation cancelled; no completed result is available.")
            outcome = "completed"
        except InvestigationCancelled as exc:
            outcome, reason = "cancelled", str(exc)
        except Exception as exc:
            error = {"type": type(exc).__name__, "message": str(exc)[:2000]}
        finally:
            with self._lock:
                job.update(status=outcome, error=error, finished_at=_now(), current_stage=None, can_cancel=False)
                if outcome == "completed":
                    job.update(result=deepcopy(result), investigation_id=result["id"])
                elif outcome == "cancelled":
                    self._skip_unfinished(job, reason)
                else:
                    for stage in job["stages"]:
                        if stage["status"] == "running":
                            stage.update(status="failed", finished_at=_now(), message=(error or {}).get("message", "Worker stopped."))
                    self._skip_unfinished(job, "Not run because an earlier stage failed.")
                if self._active == key:
                    self._active = None

    @staticmethod
    def _skip_unfinished(job, message):
        for stage in job["stages"]:
            if stage["status"] in {"pending", "running"}:
                stage.update(status="skipped", finished_at=_now(), message=message[:2000])

    def shutdown(self):
        with self._lock:
            self._closed = True
            if self._active and self._active not in self._committing:
                self._cancellations[self._active].set()
                self._jobs[self._active].update(status="cancelling", cancel_requested=True, can_cancel=False)
        self._executor.shutdown(wait=True, cancel_futures=False)
