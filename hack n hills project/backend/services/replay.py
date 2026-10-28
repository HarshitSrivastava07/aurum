"""Chronological exact-contract replay. All fills are hypothetical open proxies."""
from __future__ import annotations

from datetime import timedelta
import hashlib
import json
import math

import numpy as np
import pandas as pd

from .analytics import aligned_pair, choose_contracts, prepare, clean_json
from .genome import get_spec, integer_hedge, normalize
from .costs import fill_cost, cost_components


def leg_pnl(entry: float, exit: float, lots: int, spec: dict) -> float:
    if not isinstance(lots, (int, np.integer)):
        raise ValueError("Position lots must be integers")
    return float((exit - entry) * lots * spec["trading_unit_g"] / spec["quotation_unit_g"])


def trade_cost(entry: float, exit: float, lots: int, spec: dict, cost_bps: float) -> float:
    if cost_bps < 0:
        raise ValueError("Costs cannot be negative")
    return float((abs(entry) + abs(exit)) * abs(lots) * spec["trading_unit_g"] / spec["quotation_unit_g"] * cost_bps / 10_000)


def _finite_positive(value) -> bool:
    return value is not None and pd.notna(value) and math.isfinite(float(value)) and float(value) > 0


def _fingerprint(records: list[dict]) -> str:
    return hashlib.sha256(json.dumps(clean_json(records), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _frozen_pair(data: pd.DataFrame, config: dict) -> tuple[dict, str | None]:
    """Resolve automatic identity using only the first decision day's information."""
    if data.empty:
        return config, None
    after = data if not config.get("start") else data.loc[data.date >= config["start"]]
    pair = config.get("pair", ["GOLDM", "GOLDTEN"])
    days_a = set(after.loc[after.symbol == pair[0], "date"])
    overlap = sorted(days_a & set(after.loc[after.symbol == pair[1], "date"]))
    if not overlap:
        return config, None
    date = overlap[0]
    ea, eb = choose_contracts(data.loc[data.date <= date], config)
    return {**config, "expiry_a": ea, "expiry_b": eb}, date


def replay(df: pd.DataFrame, config: dict) -> dict:
    delay, holding, exit_delay = int(config.get("execution_delay", 1)), int(config.get("holding_days", 5)), int(config.get("exit_delay", 0))
    if delay < 1:
        raise ValueError("A close-of-session signal requires an execution delay of at least one session")
    if holding < 1 or exit_delay < 0:
        raise ValueError("Holding period must be positive and exit delay nonnegative")
    data = prepare(df, config)
    locked, selected_as_of = _frozen_pair(data, config)
    frame, metadata = aligned_pair(data, locked)
    if config.get("start") and not frame.empty:
        frame = frame.loc[frame.date >= config["start"]].reset_index(drop=True)
    capital, window = float(config.get("capital", 10_000_000)), max(3, int(config.get("window", 20)))
    if capital <= 0:
        raise ValueError("Capital must be positive")
    empty = {"trades": [], "equity": [], "events": [], "metrics": {"trades": 0, "gross_pnl": 0, "net_pnl": 0, "costs": 0, "max_drawdown": 0},
             "walk_forward": [], "holdout": {"status": "insufficient_data"}, "baselines": [], "open_position": None}
    if frame.empty:
        return {**metadata, **empty, "execution_validated": False, "status": "insufficient_data", "selected_as_of": selected_as_of}
    n = len(frame)
    records = frame.to_dict("records")
    # Reserve a calendar boundary from the declared research period, not from
    # the number of future records. Stepping the cutoff must not move the split.
    plan_start = pd.Timestamp(config.get('start') or records[0]['date'])
    plan_end = pd.Timestamp(config.get('end') or config.get('cutoff') or records[-1]['date'])
    planned_holdout = (plan_start + (plan_end-plan_start)*0.8).date().isoformat()
    holdout_index = next((i for i,r in enumerate(records) if r['date'] >= planned_holdout), n)
    if holdout_index < window + 2:
        holdout_index = n  # No independent final evaluation without a training window.
    holdout_date = records[holdout_index]["date"] if holdout_index < n else None
    base_threshold = float(config.get("z_threshold", 2))
    position, pending = None, None
    trades, equity, events, folds = [], [], [], []
    realized, cash_costs, frozen_threshold, threshold = 0.0, 0.0, None, base_threshold
    invalid_execution = False
    last_training_end = None

    def finalize(pos: dict, row: dict, index: int, reason: str) -> dict:
        leg_a = leg_pnl(pos["entry_a"], row["open_a"], pos["lots_a"], pos["spec_a"])
        leg_b = leg_pnl(pos["entry_b"], row["open_b"], pos["lots_b"], pos["spec_b"])
        exit_turnover = sum(float(row[f"open_{s}"]) * abs(pos[f"lots_{s}"]) * pos[f"spec_{s}"]["trading_unit_g"] / pos[f"spec_{s}"]["quotation_unit_g"] for s in ("a", "b"))
        exit_cost = sum(fill_cost(row['date'],row[f'open_{leg}'],-pos[f'lots_{leg}'],pos[f'spec_{leg}'],config) for leg in ('a','b'))
        total_cost = pos["entry_cost"] + exit_cost
        out_factor = sum(normalize(float(row[f"open_{s}"]), pos[f"spec_{s}"])["purity_adjusted"] for s in ("a", "b")) / 2
        gold = (out_factor - pos["entry_factor"]) * pos["residual_fine_g"]
        return {"trade_id": len(trades) + 1, "signal_date": pos["signal_date"], "entry_date": pos["entry_date"], "exit_date": row["date"],
                "symbol_a": metadata["pair"][0], "symbol_b": metadata["pair"][1], "expiry_a": metadata["expiry_a"], "expiry_b": metadata["expiry_b"],
                "lots_a": pos["lots_a"], "lots_b": pos["lots_b"], "entry_a": pos["entry_a"], "entry_b": pos["entry_b"], "exit_a": row["open_a"], "exit_b": row["open_b"],
                "gross_pnl": leg_a + leg_b, "leg_a_pnl": leg_a, "leg_b_pnl": leg_b, "costs": total_cost, "exit_cost": exit_cost,
                "net_pnl": leg_a + leg_b - total_cost, "gold_factor_contribution": gold, "relative_value_contribution": leg_a + leg_b - gold, "unexplained": 0.0,
                "residual_fine_g": pos["residual_fine_g"], "gross_notional": pos["gross_notional"], "holding_sessions": index - pos["entry_index"],
                "exit_reason": reason, "phase": pos["phase"], "execution_proxy": "subsequent common-session Open; historical executability unverified",
                "threshold_at_signal": pos["threshold"], "training_end": pos["training_end"], "spec_id_a": pos["spec_a"].get("spec_id"), "spec_id_b": pos["spec_b"].get("spec_id"),
                "entry_cost_breakdown":pos['entry_cost_breakdown'],
                "exit_cost_breakdown":{leg:cost_components(row['date'],row[f'open_{leg}'],-pos[f'lots_{leg}'],pos[f'spec_{leg}'],config) for leg in ('a','b')},
                "mode": config.get("mode", "real")}

    for index, row in enumerate(records):
        day = row["date"]
        in_holdout = index >= holdout_index
        if index == holdout_index:
            frozen_threshold = threshold
            # No position selected during fitting can carry a P&L into holdout metrics.
            if pending:
                events.append({"date": day, "type": "cancelled", "reason": "holdout boundary", "signal_date": pending["signal_date"]})
                pending = None
        specs = [get_spec(s, day, e, mode=config.get("mode", "real")) for s, e in zip(metadata["pair"], (metadata["expiry_a"], metadata["expiry_b"]))]
        opens_available = _finite_positive(row.get("open_a")) and _finite_positive(row.get("open_b"))
        if position:
            lifecycle_ok = row["lifecycle_a"].get("exit_eligible", row["entry_eligible"]) and row["lifecycle_b"].get("exit_eligible", row["entry_eligible"])
            changed = any(spec is None or spec.get("spec_id") != position[f"spec_{leg}"].get("spec_id") for spec, leg in zip(specs, ("a", "b")))
            deadline = position.get("exit_deadline")
            due = index >= position["exit_index"] or (deadline and day >= deadline) or index == holdout_index
            if (not lifecycle_ok or changed) and not position.get("invalid"):
                invalid_execution = True
                position["invalid"] = True
                events.append({"date": day, "type": "execution_invalid", "reason": "Lifecycle or specification changed before a verifiable exit observation"})
            if due and not position.get("invalid"):
                if opens_available:
                    reason = "holdout_boundary" if index == holdout_index else "lifecycle_deadline" if deadline and day >= deadline else "planned_horizon"
                    trade = finalize(position, row, index, reason)
                    trades.append(trade)
                    realized += trade["gross_pnl"]
                    cash_costs += trade["exit_cost"]
                    events.append({"date": day, "type": "exit", "trade_id": trade["trade_id"], "reason": reason})
                    position = None
                else:
                    events.append({"date": day, "type": "exit_deferred", "reason": "Missing genuine Open for a held contract"})
        if pending and index >= pending["due"] and position is None:
            reason = None
            if not opens_available:
                reason = "Missing genuine Open; no close/settlement substitution"
            elif not row["entry_eligible"]:
                reason = "Unknown, tender-period or expired contract lifecycle"
            elif any(s is None for s in specs):
                reason = "Missing historical specification"
            elif any(s.get("spec_id") != pending[f"spec_id_{leg}"] for s, leg in zip(specs, ("a", "b"))):
                reason = "Specification changed since signal"
            tender_dates = [row[f"lifecycle_{leg}"].get("tender_start") for leg in ("a", "b")]
            boundary = min(tender_dates) if all(tender_dates) else None
            # Calendar cushion is conservative; it is not an exchange holiday calendar.
            if boundary and pd.Timestamp(day) + timedelta(days=2 * (holding + exit_delay) + 2) >= pd.Timestamp(boundary):
                reason = "Insufficient calendar cushion before tender; planned entry suppressed"
            if reason:
                events.append({"date": day, "type": "entry_blocked", "reason": reason, "signal_date": pending["signal_date"]})
            else:
                liquidity_limit = min(int(config.get("max_lots", 100)), max(0, int(pending["volume_limit"])))
                available_capital = capital + realized - cash_costs
                hedge = integer_hedge(specs[0], specs[1], row["open_a"], row["open_b"], available_capital, max_lots=liquidity_limit) if liquidity_limit and available_capital > 0 else {"lots_a": 0, "lots_b": 0}
                if hedge.get("lots_a", 0) and hedge.get("lots_b", 0):
                    sign = -1 if pending["zscore"] > 0 else 1
                    qa, qb = int(abs(hedge["lots_a"]) * sign), int(-abs(hedge["lots_b"]) * sign)
                    turnover = sum(row[f"open_{leg}"] * abs(q) * spec["trading_unit_g"] / spec["quotation_unit_g"] for leg, q, spec in zip(("a", "b"), (qa, qb), specs))
                    entry_cost = sum(fill_cost(day,row[f'open_{leg}'],q,spec,config) for leg,q,spec in zip(('a','b'),(qa,qb),specs))
                    grams = sum(q * spec["trading_unit_g"] * spec["purity"] / (1000 if spec["purity"] > 1 else 1) for q, spec in zip((qa, qb), specs))
                    position = {"signal_date": pending["signal_date"], "entry_date": day, "entry_index": index, "exit_index": index + holding + exit_delay,
                                "entry_a": float(row["open_a"]), "entry_b": float(row["open_b"]), "lots_a": qa, "lots_b": qb,
                                "spec_a": specs[0], "spec_b": specs[1], "entry_cost": entry_cost, "gross_notional": turnover, "residual_fine_g": grams,
                                "entry_factor": sum(normalize(row[f"open_{leg}"], spec)["purity_adjusted"] for leg, spec in zip(("a", "b"), specs)) / 2,
                                "exit_deadline": (pd.Timestamp(boundary) - timedelta(days=1)).date().isoformat() if boundary else None,
                                "phase": "holdout" if in_holdout else "walk_forward", "threshold": pending["threshold"], "training_end": pending["training_end"]}
                    position['entry_cost_breakdown']={leg:cost_components(day,row[f'open_{leg}'],q,spec,config) for leg,q,spec in zip(('a','b'),(qa,qb),specs)}
                    cash_costs += entry_cost
                    events.append({"date": day, "type": "entry", "signal_date": pending["signal_date"], "lots_a": qa, "lots_b": qb, "phase": position["phase"]})
                else:
                    events.append({"date": day, "type": "entry_blocked", "reason": "No integer hedge fits capital and previous-session liquidity limits"})
            pending = None
        unrealized = 0.0
        if position:
            unrealized = sum(leg_pnl(position[f"entry_{leg}"], row[f"price_{leg}"], position[f"lots_{leg}"], position[f"spec_{leg}"]) for leg in ("a", "b"))
        equity.append({"date": day, "equity": capital + realized + unrealized - cash_costs, "realized_gross": realized,
                       "unrealized_gross": unrealized, "costs_paid": cash_costs, "phase": "holdout" if in_holdout else "walk_forward"})
        # Refits happen after the session and use only strictly prior feature values.
        if not in_holdout and index >= 2 * window and (index - 2 * window) % window == 0:
            history = frame.iloc[max(0, index - 3 * window):index].zscore.dropna().abs()
            if len(history) >= window:
                threshold = max(base_threshold, min(4.0, float(history.quantile(0.8))))
                last_training_end = records[index - 1]["date"]
                folds.append({"training_start": records[max(0, index - 3 * window)]["date"], "training_end": last_training_end,
                              "effective_date": day, "threshold": threshold, "method": "past absolute-z 80th percentile, bounded below by configured threshold and above by 4", "observations": len(history)})
        if in_holdout:
            threshold = frozen_threshold if frozen_threshold is not None else base_threshold
        zscore = row.get("zscore")
        if position is None and pending is None and pd.notna(zscore) and abs(zscore) >= threshold:
            # Prospective full-policy gates see only data at this signal session.
            if config.get('baseline','B') == 'C':
                reason=None
                if not row['maturity_adjusted'] or row['basis_risk'] or not row['spec_verified']:
                    reason='Unresolved maturity, geographic basis or specification'
                elif not row['entry_eligible'] or not row['liquid']:
                    reason='Lifecycle or liquidity gate failed'
                elif pd.isna(row.get('robust_zscore')) or abs(row['robust_zscore'])<threshold or np.sign(row['robust_zscore'])!=np.sign(zscore):
                    reason='Robust MAD deviation does not confirm the candidate'
                else:
                    from .scenarios import ghost_market
                    stress=ghost_market(data.loc[data.date<=day],{**locked,'cutoff':day,'simulations':100},aligned=(frame.iloc[:index+1],metadata))
                    scenarios=stress.get('scenarios',[])
                    if not scenarios or any(s['median_net_pnl']<=0 or s['status']!='modeled_only' for s in scenarios):
                        reason='Prospective paired bootstrap does not survive every modeled median/cost/lifecycle stress'
                if reason:
                    events.append({'date':day,'type':'candidate_rejected','reason':reason,'information_cutoff':day})
                    continue
            if row["entry_eligible"] and row["liquid"]:
                pending = {"due": index + delay, "signal_date": day, "zscore": float(zscore), "threshold": threshold,
                           "training_end": last_training_end, "spec_id_a": row["spec_id_a"], "spec_id_b": row["spec_id_b"],
                           "volume_limit": min(float(row["volume_a"]), float(row["volume_b"])) * float(config.get("max_participation", 0.01))}
                events.append({"date": day, "type": "signal", "zscore": zscore, "threshold": threshold, "information_cutoff": day,
                               "phase": "holdout" if in_holdout else "walk_forward"})
            else:
                events.append({"date": day, "type": "suppressed", "reason": "Liquidity or lifecycle is ineligible"})
    curve = np.array([capital] + [e["equity"] for e in equity], dtype=float)
    drawdown = curve / np.maximum.accumulate(curve) - 1
    for point, value in zip(equity, drawdown[1:]):
        point['drawdown_fraction'] = float(-value)
    returns = np.diff(curve) / curve[:-1]
    gross, costs = sum(t["gross_pnl"] for t in trades), sum(t["costs"] for t in trades)
    holdout_trades = [t for t in trades if t["phase"] == "holdout"]
    training_snapshot = frame.iloc[:holdout_index][["date", "expiry_a", "expiry_b", "price_a", "price_b"]].to_dict("records")
    holdout_snapshot = frame.iloc[holdout_index:][["date", "expiry_a", "expiry_b", "price_a", "price_b"]].to_dict("records")
    metrics = {"trades": len(trades), "gross_pnl": gross, "costs": costs, "net_pnl": gross - costs, "total_equity_change": curve[-1] - capital,
               "open_position_unrealized": equity[-1]["unrealized_gross"], "max_drawdown": float(-drawdown.min()),
               "return_on_capital": (curve[-1] - capital) / capital, "daily_volatility": float(np.std(returns, ddof=1)) if len(returns) > 1 else None,
               "annualized_sharpe_descriptive": float(np.mean(returns) / np.std(returns, ddof=1) * np.sqrt(252)) if len(returns) >= 30 and np.std(returns, ddof=1) > 0 else None,
               "win_rate": sum(t["net_pnl"] > 0 for t in trades) / len(trades) if trades else None,
               "gold_factor_contribution": sum(t["gold_factor_contribution"] for t in trades), "relative_value_contribution": sum(t["relative_value_contribution"] for t in trades), "unexplained": 0.0}
    # Benchmark comparisons are fully funded and costed; directional mark is explicitly research-only.
    first, last = records[0], records[-1]
    benchmark = {"name": "gold leg A buy and hold, exact expiry", "net_pnl": None, "status": "unavailable", "execution_proxy": "Open to final observed Close mark; no verified liquidation"}
    naive_pair = {"name": "fixed long A / short B integer hedge", "net_pnl": None, "status": "unavailable",
                  "execution_proxy": "First observed Open to final Close mark; no anomaly timing or verified liquidation"}
    spec = get_spec(metadata["pair"][0], first["date"], metadata["expiry_a"], mode=config.get("mode", "real"))
    if spec and _finite_positive(first.get("open_a")):
        lots = int(capital // (first["open_a"] * spec["trading_unit_g"] / spec["quotation_unit_g"]))
        try:
            benchmark_fees = (fill_cost(first['date'], first['open_a'], lots, spec, config)
                              + fill_cost(last['date'], last['price_a'], -lots, spec, config))
        except ValueError as exc:
            benchmark['reason'] = f"Benchmark fees unavailable: {exc}"
        else:
            benchmark.update(net_pnl=leg_pnl(first["open_a"], last["price_a"], lots, spec) - benchmark_fees, costs=benchmark_fees, lots=lots,
                             status="descriptive_mark_only", entry_date=first["date"], mark_date=last["date"])
        spec_b = get_spec(metadata["pair"][1], first["date"], metadata["expiry_b"], mode=config.get("mode", "real"))
        if spec_b and _finite_positive(first.get("open_b")):
            benchmark_hedge = integer_hedge(spec, spec_b, first["open_a"], first["open_b"], capital, max_lots=int(config.get("max_lots", 100)))
            if benchmark_hedge.get("lots_a") and benchmark_hedge.get("lots_b"):
                qa, qb = int(benchmark_hedge["lots_a"]), -int(benchmark_hedge["lots_b"])
                gp = leg_pnl(first["open_a"], last["price_a"], qa, spec) + leg_pnl(first["open_b"], last["price_b"], qb, spec_b)
                try:
                    fees = sum(fill_cost(first['date'], first[f'open_{leg}'], quantity, definition, config)
                               + fill_cost(last['date'], last[f'price_{leg}'], -quantity, definition, config)
                               for leg, quantity, definition in [('a', qa, spec), ('b', qb, spec_b)])
                except ValueError as exc:
                    naive_pair['reason'] = f"Benchmark fees unavailable: {exc}"
                else:
                    naive_pair.update(net_pnl=gp - fees, gross_pnl=gp, costs=fees, lots_a=qa, lots_b=qb, status="descriptive_mark_only")
    warnings = metadata["warnings"] + ["Open fills are hypothetical, not proof of executable two-leg fills; no margin leverage is modeled.",
               "Attribution uses the mean of the two normalized legs as a gold proxy; relative-value contribution is an accounting residual, not causal alpha.",
               "Holdout parameters are frozen before its first observation; rerunning altered research configurations is a new experiment, not independent validation.",
               "Liquidity sizing uses the signal session's volume at 1% default participation; next-session realized liquidity is unknown."]
    if position:
        warnings.append("Unclosed position remains marked to market: no fabricated final liquidation or complete-trade claim")
    return clean_json({**metadata, "selected_as_of": selected_as_of, "selection": "exact contracts frozen using information available at first replay session",
                       "trades": trades, "equity": equity, "events": events, "metrics": metrics, "walk_forward": folds,
                       "holdout": {"status": "evaluated_frozen_parameters" if holdout_date else "insufficient_data", "start": holdout_date,
                                   "planned_boundary":planned_holdout,
                                   "training_end": records[holdout_index - 1]["date"] if holdout_index else None,
                                   "frozen_threshold": frozen_threshold, "training_hash": _fingerprint(training_snapshot), "snapshot_hash": _fingerprint(holdout_snapshot),
                                   "trades": len(holdout_trades), "net_pnl": sum(t["net_pnl"] for t in holdout_trades), "observations": len(holdout_snapshot)},
                       "baselines": [{"name": "no trade / cash", "net_pnl": 0.0, "assumed_interest": 0.0}, benchmark, naive_pair],
                       "open_position": {k: v for k, v in position.items() if k not in ("spec_a", "spec_b")} if position else None,
                       "pending_signal": pending, "execution_validated": False, "lifecycle_invariant_passed": not invalid_execution,
                       "status": "hypothetical_replay", "warnings": warnings})
