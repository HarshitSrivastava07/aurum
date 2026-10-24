"""Executable adversarial invariants with explicit unresolved outcomes."""
import math
from datetime import date,timedelta
import pandas as pd
from .analytics import analyze_pair, clean_json
from .genome import get_spec, normalize, lifecycle
from .replay import leg_pnl
from .costs import fill_cost


def audit(df, config, analysis=None, replay_result=None, investigation=None, prior_experiments=None):
    analysis = analysis or analyze_pair(df, config)
    replay_result = replay_result or {}
    cutoff = min([str(x) for x in [config.get("cutoff"), config.get("end")] if x], default=(df.date.max() if not df.empty else None))
    data = df.loc[df.date <= cutoff].copy() if cutoff and not df.empty else df.copy()
    trades = replay_result.get("trades", [])
    checks = []

    def add(key, description, invariant, evidence, procedure, status, explanation, severity="high"):
        checks.append({"attack_id": key, "description": description, "target_invariant": invariant,
                       "input_evidence": clean_json(evidence), "procedure": procedure, "output": status,
                       "status": status, "severity": severity, "explanation": explanation,
                       "affected_investigation": investigation})

    def passed(ok):
        return "pass" if ok else "fail"

    if data.empty:
        add("DATE", "Wrong date parsing", "ISO actual trading dates", {"rows": 0}, "Inspect canonical dates and requested/returned provenance", "not-evaluable", "No daily observations are available")
    else:
        actual = pd.to_datetime(data.date, errors="coerce")
        valid = actual.notna().all() and (actual.dt.strftime("%Y-%m-%d") == data.date).all()
        mismatch = int(((data.get("requested_date", pd.Series(index=data.index, dtype=object)).notna()) & (data.get("requested_date", data.date) != data.date)).sum())
        add("DATE", "Wrong date parsing", "Actual dates retained; requested dates do not relabel observations", {"rows": len(data), "mismatches": mismatch}, "Parse ISO dates and compare requested versus returned values", passed(valid and mismatch == 0), "Date mismatches require import quarantine; holidays are never inferred from missing rows")

    specs = [get_spec(s, (cutoff or (data.date.max() if not data.empty else "2025-01-01")), analysis.get(f"expiry_{leg}"), mode=config.get("mode", "real")) for s, leg in zip(config["pair"], ("a", "b"))]
    for key, field, explanation in [("PURITY", "purity", "Independent metal-content inverse identity"), ("QUOTATION", "quotation_unit_g", "Trading units and quotation units remain distinct")]:
        ok = all(specs)
        values = []
        if ok:
            for spec in specs:
                n = normalize(100000, spec)
                expected = 100000 / spec["quotation_unit_g"] / spec["purity"]
                ok = ok and math.isclose(n["purity_adjusted"], expected, rel_tol=1e-12)
                values.append({"spec_id": spec["spec_id"], field: spec[field], "normalized_test_price": n["purity_adjusted"]})
        add(key, f"Wrong {key.lower()} normalization", "Monetary units follow selected specifications", values, "Normalize INR100000 and independently invert fine-metal units", passed(ok) if all(specs) else "not-evaluable", explanation)

    lots_ok = all(isinstance(t.get(k), int) and t[k] != 0 for t in trades for k in ("lots_a", "lots_b"))
    add("INTEGER", "Fractional or incorrect lot sizing", "Nonzero integer quantities", {"trades": len(trades)}, "Check signed lot types and quantities on every filled trade", passed(lots_ok) if trades else "not-evaluable", "No trades means sizing cannot be verified for this experiment")
    ids_ok = all(t.get("expiry_a") == analysis.get("expiry_a") and t.get("expiry_b") == analysis.get("expiry_b") for t in trades)
    add("EXPIRY", "Invalid expiry matching", "Held IDs match selected expiry-specific contracts", {"expiry_a": analysis.get("expiry_a"), "expiry_b": analysis.get("expiry_b")}, "Compare all held contract IDs to selected identities", passed(ids_ok) if trades else "not-evaluable", "No near-month stitching is allowed")
    add("ROLL", "Contract roll contamination", "Each trade has unchanged expiry identity", {"trades": len(trades)}, "Require exact source rows for both entry and exit using same symbols and expiries", passed(ids_ok) if trades else "not-evaluable", "Contract changes require separate trades and costs")

    if len(data) and cutoff:
        future = df.copy()
        future_count=int((df.date>cutoff).sum())
        probe_count=0
        bounded={**config,'cutoff':cutoff}
        if not future_count:
            # Explicit adversarial test fixture only: these fabricated outliers
            # are never saved as observations or used for a research outcome.
            # Keep the declared input mode to exercise the time gate itself,
            # not merely the separate mixed-mode validation guard.
            probe_day=(date.fromisoformat(cutoff)+timedelta(days=1)).isoformat()
            probes=[]
            for leg,symbol in zip(('a','b'),config['pair']):
                expiry=analysis.get(f'expiry_{leg}')
                selected=data.loc[(data.symbol==symbol)&(data.expiry==expiry)]
                if expiry and expiry>=probe_day and not selected.empty:
                    row=selected.iloc[-1].to_dict()
                    row.update(date=probe_day,source_file='AUDIT_ONLY_SYNTHETIC_FUTURE_PROBE',source_hash='AUDIT_ONLY_NOT_MARKET_HISTORY')
                    probes.append(row)
            # A one-leg probe cannot exercise the paired decision engine.
            # In that case the check is unresolved, not evidence of leakage.
            if len(probes)==len(config['pair']):
                future=pd.concat([future,pd.DataFrame(probes)],ignore_index=True)
                probe_count=len(probes)
        for column in ("open", "high", "low", "close", "settlement"):
            if column in future:
                future.loc[future.date > cutoff, column] = future.loc[future.date > cutoff, column] * 99
        mutated = analyze_pair(future, bounded)
        same = clean_json(mutated) == clean_json(analysis)
        control_changed=True
        if probe_count:
            control=analyze_pair(future,{**config,'cutoff':probe_day,'end':probe_day})
            control_changed=clean_json(control)!=clean_json(analysis)
        add("FUTURE", "Future-data leakage", "Post-cutoff price mutation does not alter decisions", {"cutoff": cutoff, "withheld_market_rows":future_count,'audit_only_synthetic_probe_rows':probe_count,'probe_is_market_history':False,'positive_control_changed':control_changed}, "Multiply post-cutoff prices by99 and rerun Mirage; if no withheld rows exist, inject clearly marked audit-only future probes and verify a relaxed cutoff sees them", passed(same and control_changed) if future_count or probe_count else "not-evaluable", "Only the invariant result is retained. Probe prices never enter source snapshots, research returns, analogs or certificates as market observations.", "critical")
    else:
        add("FUTURE", "Future-data leakage", "Decision engine cannot inspect future outcomes", {"cutoff": cutoff}, "Run cutoff mutation test", "not-evaluable", "A selected cutoff and withheld observations are required", "critical")
    lag = all(t["entry_date"] > t["signal_date"] for t in trades)
    add("SAME_DAY", "Same-day settlement fills", "Signal precedes hypothetical Open fill", {"trades": len(trades)}, "Compare each signal date with its entry date", passed(lag) if trades else "not-evaluable", "Displayed Open prices still do not establish actual execution", "critical")

    source_ok, life_ok, costs_ok, pnl_ok = True, True, True, True
    exposure = []
    for trade in trades:
        gross = 0
        expected_cost = 0
        for leg in ("a", "b"):
            symbol, expiry = trade[f"symbol_{leg}"], trade[f"expiry_{leg}"]
            spec = get_spec(symbol, trade["entry_date"], expiry, mode=config["mode"])
            for phase in ("entry", "exit"):
                rows = data.loc[(data.symbol == symbol) & (data.expiry == expiry) & (data.date == trade[f"{phase}_date"])]
                exact = len(rows) == 1 and pd.notna(rows.iloc[0].get("open")) and math.isclose(float(rows.iloc[0]["open"]), trade[f"{phase}_{leg}"], rel_tol=1e-10)
                source_ok &= exact
                life_ok &= len(rows) == 1 and lifecycle(rows.iloc[0].to_dict(), spec)["entry_eligible"]
            if spec and isinstance(trade[f"lots_{leg}"], int):
                gross += leg_pnl(trade[f"entry_{leg}"], trade[f"exit_{leg}"], trade[f"lots_{leg}"], spec)
                expected_cost += fill_cost(trade['entry_date'],trade[f'entry_{leg}'],trade[f'lots_{leg}'],spec,config)+fill_cost(trade['exit_date'],trade[f'exit_{leg}'],-trade[f'lots_{leg}'],spec,config)
            else:
                pnl_ok = False
        costs_ok &= math.isclose(expected_cost, trade["costs"], abs_tol=1e-6)
        pnl_ok &= math.isclose(gross - trade["costs"], trade["net_pnl"], abs_tol=1e-6) and math.isclose(trade.get("gold_factor_contribution",0)+trade.get("relative_value_contribution",0)+trade.get("unexplained",0), gross, abs_tol=1e-6)
        exposure.append(trade.get("residual_fine_g"))
    for key, title, invariant, ok, procedure in [
        ("SOURCE", "Missing execution observations", "Actual same-contract Open exists", source_ok, "Rejoin each trade to exact dated raw observations"),
        ("DELIVERY", "Delivery-window violation", "Every modeled fill satisfies Genome", life_ok and replay_result.get("lifecycle_invariant_passed", True), "Re-evaluate lifecycle at each entry and exit"),
        ("COST", "Underestimated transaction costs", "Every leg includes entry and exit fees/slippage", costs_ok, "Independently reconstruct signed-lot turnover and bps costs"),
        ("ATTRIBUTION", "Incorrect performance attribution", "Leg P&L minus costs equals net; components reconcile", pnl_ok, "Recompute actual contract-money P&L and reconcile accounting")]:
        add(key, title, invariant, {"trades": len(trades)}, procedure, passed(ok) if trades else "not-evaluable", "Cost rates are assumptions; accounting reconciliation does not establish causal attribution", "critical" if key in ("SOURCE","DELIVERY") else "high")
    liquid = [r for r in analysis.get("series", []) if r.get("candidate")]
    add("LIQUIDITY", "Weak liquidity", "Candidate sessions satisfy declared volume/OI screens", {"candidates": len(liquid)}, "Inspect candidate liquidity flags and previous-session participation sizing", passed(all(r.get("liquid") for r in liquid)) if liquid else "not-evaluable", "Daily volume and OI cannot prove concurrent executable liquidity")
    add("SNOOPING", "Selective research reporting", "All investigation requests retained", {"prior_experiments": prior_experiments}, "Count prior requests in local hypothesis ledger", "pass" if prior_experiments is not None else "not-evaluable", "External/unrecorded experiments cannot be excluded; this checks local recording only")
    holdout = replay_result.get("holdout", {})
    frozen = holdout.get("start") and holdout.get("training_end") and holdout["training_end"] < holdout["start"]
    add("RETUNING", "Repeated held-out parameter optimization", "Parameters fixed before holdout", holdout, "Verify holdout boundary, training hash and prior experiment count", "not-evaluable" if not frozen or prior_experiments is None or prior_experiments > 0 else "pass", "Repeated requests expose the final sample; a reused holdout is no longer untouched")
    sample = holdout.get("trades", 0)
    add("CONFIDENCE", "Unreliable statistical confidence", "Outcome count supports meaningful uncertainty", {"holdout_trades": sample}, "Require at least30 completed holdout trades before inferential claims", "pass" if sample >= 30 else "not-evaluable", "No calibrated probability of profit or statistical significance is claimed")
    add("NEUTRALITY", "False gold-neutral claim", "Residual fine-metal exposure quantified", {"residual_fine_grams": exposure}, "Inspect reported residual grams for every position", passed(all(x is not None and math.isfinite(x) for x in exposure)) if exposure else "not-evaluable", "Nonzero residual exposure remains directional risk")
    n = len(analysis.get("series", []))
    add("SAMPLE", "Insufficient estimation sample", "At least2 rolling windows of paired observations", {"paired_sessions": n, "window": config.get("window",20)}, "Compare aligned sample to required estimation windows", 'pass' if n>=2*config.get('window',20) else 'not-evaluable', "A minimum estimation sample is not proof of predictive validity")
    locs = [s.get("quote_location") if s else None for s in specs]
    add("GEOGRAPHY", "Misleading geographical basis", "Matching quote bases or estimated adjustment", {"quote_locations": locs}, "Compare date-effective specification quote locations", "pass" if all(locs) and locs[0] == locs[1] else "not-evaluable", "Unmatched locations remain unresolved; normalized spread is not arbitrage")
    imputations = int(data.get("validation_status", pd.Series(dtype=str)).astype(str).str.contains("imput", case=False).sum())
    add("IMPUTATION", "Silent imputation", "No substituted prices presented as observed", {"flagged_rows": imputations}, "Inspect validation labels and exact-source execution reconciliation", passed(imputations == 0 and source_ok) if len(data) else "not-evaluable", "Missing sessions stay missing; no fill-forward in ingestion")
    modes = sorted(data["mode"].unique().tolist()) if len(data) and "mode" in data else []
    add("SYNTHETIC", "Synthetic/real mixing", "One declared mode per calculation", {"modes": modes, "requested_mode": config["mode"]}, "Compare every row's provenance mode with configuration", passed(modes == [config["mode"]]) if modes else "not-evaluable", "Synthetic evidence cannot validate historical MCX profitability", "critical")
    counts = {s: sum(x["status"] == s for x in checks) for s in ("pass", "fail", "not-evaluable")}
    return {"checks": checks, "summary": counts, "all_evaluated_pass": counts["fail"] == 0 and counts["not-evaluable"] == 0,
            "policy": "Untested or non-evaluable invariants never count as passes."}
