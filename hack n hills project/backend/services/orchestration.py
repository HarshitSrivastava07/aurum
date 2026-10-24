"""Research orchestration and reproducible evidence certificates."""
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
from pydantic import BaseModel
from .analytics import analyze_pair, curve_analysis, clean_json, choose_contracts
from .analogs import find_analogs
from .genome import list_specs
from .scenarios import ghost_market, survival_map, REQUIRED_SCENARIOS
from .replay import replay
from .red_team import audit
from .ledger import canonical, digest
from .demo import LABEL

VERSION = "0.1.0"
INVESTIGATION_STAGES = (
    ("snapshot", "Freeze data and exact contracts"),
    ("mirage", "Normalize and investigate relative value"),
    ("curves", "Inspect historical futures curves"),
    ("analogs", "Find prior historical analogs"),
    ("replay", "Replay chronological execution"),
    ("red_team", "Run adversarial checks"),
    ("ghost", "Model adverse market scenarios"),
    ("survival", "Evaluate cost and delay sensitivity"),
    ("baseline_comparison", "Compare fixed research policies"),
    ("certificate", "Preserve the evidence certificate"),
)


class InvestigationCancelled(RuntimeError):
    """A cancellation request observed at a safe stage boundary."""


def _check_cancel(cancel_requested):
    if cancel_requested and cancel_requested():
        raise InvestigationCancelled("Investigation cancelled before the next stage; no certificate was saved.")


def _progress(callback, investigation, stage, status, message=""):
    if callback:
        callback({"investigation_id": investigation, "stage": stage, "status": status, "message": message})


def _stage_outcome(name, output):
    """Describe actual engine limitations without changing financial outputs."""
    if name == "curves":
        insufficient = [symbol for symbol, curve in output.items()
                        if isinstance(curve, dict) and curve.get("classification") == "insufficient_curve"]
        if insufficient:
            return "warning", "Insufficient curve observations for " + ", ".join(insufficient) + "."
        if any(isinstance(curve, dict) and curve.get("warnings") for curve in output.values()):
            return "warning", "Curves computed with reported model and delivery-basis limitations."
    if name == "red_team":
        summary = output.get("summary", {})
        failed, unknown = summary.get("fail", 0), summary.get("not-evaluable", 0)
        if failed or unknown:
            return "warning", f"{failed} checks failed; {unknown} checks could not be evaluated."
    status = str(output.get("status", ""))
    limitations = ("insufficient", "unavailable", "blocked", "no_feasible", "no_eligible")
    if any(term in status for term in limitations):
        return "warning", str(output.get("message") or status.replace("_", " "))
    if output.get("warnings"):
        return "warning", f"Calculation finished with {len(output['warnings'])} reported warnings."
    return "completed", str(output.get("message") or status.replace("_", " ") or "Calculation finished.")


def determine_verdict(outputs, has_data=True):
    audit_summary=outputs['red_team']['summary']
    replayed=outputs['replay']
    holdout=replayed.get('holdout',{})
    ghost=outputs['ghost']
    scenarios=ghost.get('scenarios',[])
    stress_complete=(ghost.get('status')=='simulated' and
        {s.get('name') for s in scenarios}==REQUIRED_SCENARIOS and
        all(s.get('status')=='modeled_only' and s.get('lifecycle_eligible') and s.get('liquidity_eligible') for s in scenarios))
    if audit_summary.get('fail',0):
        return 'REJECTED'
    if not has_data or audit_summary.get('not-evaluable',0) or holdout.get('trades',0)<30 or replayed.get('open_position') or not stress_complete:
        return 'INSUFFICIENT EVIDENCE'
    latest=outputs['mirage'].get('latest')
    if not (latest and latest.get('candidate')) or holdout.get('net_pnl',0)<=0 or any(s.get('median_net_pnl',0)<=0 for s in scenarios):
        return 'REJECTED'
    return 'SURVIVES MODELED TESTS'


class StageResult(BaseModel):
    name: str
    result: dict


def code_hash():
    root = Path(__file__).resolve().parents[1]
    return digest({str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*.py"))})


def run_stages(frame, config, investigation=None, prior_experiments=0, ledger=None,
               progress=None, cancel_requested=None):
    result = {}
    def stage(name, function):
        _check_cancel(cancel_requested)
        _progress(progress, investigation, name, "running")
        if ledger:
            ledger.append(investigation, "stage_started", {"stage": name})
        try:
            output = StageResult(name=name, result=clean_json(function())).result
        except Exception as exc:
            _progress(progress, investigation, name, "failed", str(exc))
            raise
        result[name] = output
        if ledger:
            ledger.append(investigation, "stage_completed", {"stage": name, "digest": digest(output), "status": output.get("status")})
        state, message = _stage_outcome(name, output)
        _progress(progress, investigation, name, state, message)
        return output
    analysis = stage("mirage", lambda: analyze_pair(frame, config))
    as_of = config.get("cutoff") or config.get("end") or (frame.date.max() if len(frame) else "2025-01-01")
    stage("curves", lambda: {s: curve_analysis(frame, as_of, s) for s in config["pair"]})
    stage("analogs", lambda: find_analogs(frame, config))
    replayed = stage("replay", lambda: replay(frame, config))
    stage("red_team", lambda: audit(frame, config, analysis, replayed, None, prior_experiments))
    stage("ghost", lambda: ghost_market(frame, config))
    stage("survival", lambda: survival_map(frame, config))
    def baselines():
        rows=[]
        for baseline,name in [('A','Normalized spread scanner'),('B','Maturity-aware model'),('C','Full prospective investigation policy')]:
            model=replayed if config.get('baseline','C')==baseline else replay(frame,{**config,'baseline':baseline})
            rows.append({'baseline':baseline,'name':name,**model['metrics'],'holdout':model.get('holdout'),
                         'candidate_rejections':sum(e['type']=='candidate_rejected' for e in model.get('events',[])),
                         'accepted_signals':sum(e['type']=='signal' for e in model.get('events',[]))})
        return {'results':rows,'policy':'Identical exact contracts, dates, liquidity, capital and execution assumptions. A omits maturity adjustment. B adds supported curve-relative adjustment. C adds robust-score, basis, lifecycle and prospective joint-bootstrap stress gates. No best-baseline selection is performed.'}
    stage('baseline_comparison',baselines)
    return result


def investigate(storage, ledger, config, progress=None, cancel_requested=None):
    config = dict(config)
    key = str(uuid.uuid4())
    active_stage = None
    try:
        _check_cancel(cancel_requested)
        active_stage = "snapshot"
        _progress(progress, key, active_stage, "running")
        prior = ledger.count_similar(config["mode"], config["pair"])
        ledger.append(key, "request", config)
        directory = ledger.directory(key)
        directory.mkdir()
        limit = min([x for x in [config.get("end"), config.get("cutoff")] if x], default=None)
        frame = storage.load(config["mode"], end=limit, symbols=config["pair"])
        if len(frame) > 100_000:
            raise ValueError("Investigation exceeds100000 observations; choose a shorter dataset/window")
        if not frame.empty:
            config["cutoff"] = limit or frame.date.max()
            # Preserve enough prior rows for rolling fit, but freeze expiry selection
            # using only the first observed research session.
            after = frame if not config.get("start") else frame.loc[frame.date >= config["start"]]
            if not after.empty:
                first = after.date.min()
                ea, eb = choose_contracts(frame.loc[frame.date <= first], config)
                config["expiry_a"], config["expiry_b"] = ea, eb
        snapshot_hash = digest(frame.to_dict("records"))
        frame.to_parquet(directory / "snapshot.parquet", index=False)
        specs = list_specs(config["mode"])
        (directory / "specifications.json").write_text(canonical(specs), encoding="utf-8")
        ledger.append(key, "preregistered", {"configuration": config, "prior_experiments": prior, "snapshot_hash": snapshot_hash,
                       "planned_tests": ["Mirage deviations", "prior analog outcomes", "21 adversarial invariants", "paired block bootstrap", "chronological exact-contract replay", "cost/delay sensitivity"],
                       "hypothesis": "The selected exact-contract residual remains unusual after metal-content and supported maturity adjustments, and survives modeled costs and stress."})
        _progress(progress, key, active_stage, "completed" if len(frame) else "warning",
                  f"Preserved {len(frame)} observations." if len(frame) else "No observations are available; evidence will remain insufficient.")
        active_stage = None
        outputs = run_stages(frame, config, key, prior, ledger, progress, cancel_requested)
        _check_cancel(cancel_requested)
        active_stage = "certificate"
        # Job callbacks serialize this entry with cancellation: once saving begins,
        # a new cancellation is refused until the persisted outcome is known.
        _progress(progress, key, active_stage, "running")
        audit_summary = outputs["red_team"]["summary"]
        latest = outputs["mirage"].get("latest")
        has_candidate = bool(latest and latest.get("candidate"))
        holdout = outputs["replay"].get("holdout", {})
        verdict=determine_verdict(outputs,not frame.empty)
        source_authenticity_verified = False
        provenance = "SYNTHETIC TEST DATA" if config["mode"] == "synthetic" else "IMPORTED UNVERIFIED DATA"
        if config["mode"] == "real" and not source_authenticity_verified and verdict == "SURVIVES MODELED TESTS":
            verdict = "INSUFFICIENT EVIDENCE"
        sources = frame[["source_file", "source_hash"]].drop_duplicates().to_dict("records") if len(frame) else []
        certificate = {"id": key, "timestamp": datetime.now(timezone.utc).isoformat(), "historical_information_cutoff": config.get("cutoff"),
            "provenance": provenance, "source_authenticity_verified": source_authenticity_verified,
            "provenance_gate": {"status": "synthetic" if config["mode"] == "synthetic" else "unverified",
                                "message": "Synthetic test data cannot establish market performance." if config["mode"] == "synthetic" else "Imported source authenticity has not been independently verified; a positive real-data conclusion is blocked."},
            "config": config, "mode_label": LABEL if config["mode"] == "synthetic" else "REAL MCX IMPORT MODE — provenance supplied by importer; source authenticity is not independently certified",
            "contract_names_and_expiries": {"pair": config["pair"], "expiry_a": config.get("expiry_a"), "expiry_b": config.get("expiry_b")},
            "sources": sources, "official_references": ["https://www.mcxindia.com/market-data/bhavcopy", "https://www.mcxindia.com/products/bullion/gold"],
            "data_quality": {"snapshot_rows": len(frame), "sessions": int(frame.date.nunique()) if len(frame) else 0,
                "start": frame.date.min() if len(frame) else None, "end": frame.date.max() if len(frame) else None,
                "source_hashes": sorted(frame.source_hash.unique().tolist()) if len(frame) else [],
                "warning_rows": int((frame.validation_status == "warning").sum()) if len(frame) else 0},
            "applicable_specifications": specs, "specifications_hash": digest(specs), "snapshot_hash": snapshot_hash,
            "model_version": VERSION, "code_hash": code_hash(), "seed": config["seed"], "prior_experiments": prior,
            "outputs": outputs, "result_hash": digest(outputs), "verdict": verdict,
            "execution_feasibility": "Unverified" if not len(frame) or config["mode"] == "synthetic" else "Blocked by known restrictions" if latest and not latest.get("entry_eligible") else "Unverified",
            "message": outputs["mirage"]["message"], "ledger_reference": key,
            "cost_assumptions": {"cost_bps_per_turnover": config["cost_bps"], "slippage_bps_per_turnover": config["slippage_bps"], "verified_historical_fee_schedule": False},
            "limitations": ["No verified two-leg execution is established by daily OHLC.", "Bootstrap frequencies are not calibrated probabilities.",
                "Normalization is INR per fine gram; multiply by9.99 for a common10g .999 reference.",
                "Metal normalization leaves location, tax, maturity and delivery basis risks.",
                "A reused held-out sample is not untouched; all runs are recorded locally.",
                "Attribution is an accounting decomposition using a two-leg mean price factor; relative-value residual is not causal alpha.",
                "No cryptographic tamper resistance is claimed for local artifacts."]}
        ledger.append(key, "conclusion", {"verdict": verdict, "result_hash": certificate["result_hash"], "execution_feasibility": certificate["execution_feasibility"]})
        certificate["ledger"] = ledger.events(key)
        pending_certificate = directory / "certificate.json.tmp"
        pending_certificate.write_text(canonical(certificate), encoding="utf-8")
        pending_certificate.replace(directory / "certificate.json")
        _progress(progress, key, active_stage, "completed", f"Certificate saved: {verdict}.")
        return certificate
    except InvestigationCancelled as exc:
        ledger.append(key, "cancelled", {"reason": str(exc)})
        raise
    except Exception as exc:
        if active_stage:
            _progress(progress, key, active_stage, "failed", str(exc))
        ledger.append(key, "failed", {"type": type(exc).__name__, "reason": str(exc)})
        raise


def reproduce(ledger, key):
    cert = ledger.get(key)
    directory = ledger.directory(key)
    frame = pd.read_parquet(directory / "snapshot.parquet")
    if digest(frame.to_dict("records")) != cert["snapshot_hash"]:
        raise ValueError("Snapshot hash mismatch; reproduction refused")
    if digest(list_specs(cert["config"]["mode"])) != cert["specifications_hash"]:
        raise ValueError("Specification registry changed; restore preserved specification snapshot before reproduction")
    if code_hash() != cert["code_hash"]:
        raise ValueError("Engine code changed; reproduce with the recorded model version")
    outputs = run_stages(frame, cert["config"], prior_experiments=cert["prior_experiments"])
    actual = digest(outputs)
    result = {"id": key, "match": actual == cert["result_hash"], "original_hash": cert["result_hash"], "reproduced_hash": actual,
              "snapshot_hash": cert["snapshot_hash"], "seed": cert["seed"]}
    ledger.append(key, "reproduction", result)
    return result
