"""Paired block-bootstrap robustness experiments; never calibrated profit odds."""
from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import pandas as pd

from .analytics import aligned_pair, clean_json
from .genome import get_spec, integer_hedge
from .replay import replay
from .costs import fill_cost

REQUIRED_SCENARIOS = frozenset(['Base paired bootstrap','Increased transaction costs','Execution slippage',
    'Delayed entries','Delayed exits','Higher gold volatility','Correlated adverse movements',
    'Residual spread expansion','Thin liquidity','Contract expiry restrictions','Failed hedge execution','Combined stress'])


def paired_block_bootstrap(returns: np.ndarray, simulations: int, horizon: int, block_length: int, seed: int) -> np.ndarray:
    values = np.asarray(returns, dtype=float)
    if values.ndim != 2 or values.shape[1] != 2 or len(values) < 2 or not np.isfinite(values).all():
        raise ValueError("Finite paired two-leg returns are required")
    if not 1 <= simulations <= 10000 or not 1 <= horizon <= 126:
        raise ValueError("Simulation size or horizon exceeds bounded resource limits")
    rng = np.random.default_rng(int(seed))
    # Only the modeled horizon can be consumed. A longer block otherwise
    # allocates simulations * history_length indexes before truncating them.
    block = max(1, min(int(block_length), len(values), horizon))
    starts = rng.integers(0, len(values), size=(simulations, math.ceil(horizon / block)))
    indexes = ((starts[:, :, None] + np.arange(block)[None, None, :]) % len(values)).reshape(simulations, -1)[:, :horizon]
    return values[indexes]


def _summary(outcomes: np.ndarray) -> dict:
    return {"median_net_pnl": float(np.median(outcomes)), "mean_net_pnl": float(np.mean(outcomes)),
            "worst_net_pnl": float(np.min(outcomes)), "p05_net_pnl": float(np.quantile(outcomes, 0.05)),
            "p95_net_pnl": float(np.quantile(outcomes, 0.95)),
            "positive_scenario_rate": float(np.mean(outcomes > 0)),
            "expected_shortfall_05": float(np.mean(outcomes[outcomes <= np.quantile(outcomes, 0.05)])) if len(outcomes) >= 200 else None}


def ghost_market(df: pd.DataFrame, config: dict, aligned=None) -> dict:
    frame, meta = aligned if aligned is not None else aligned_pair(df, config)
    # The replay caller passes an already cutoff-limited prefix of its immutable
    # aligned frame. Copy metadata because this routine appends fee warnings.
    meta = {**meta,'warnings':list(meta.get('warnings',[]))}
    minimum = max(20, int(config.get("window", 20)))
    if frame.empty or len(frame) <= minimum:
        return {**meta, "status": "insufficient_data", "scenarios": [], "cost_sensitivity": [], "sample_size": max(0, len(frame) - 1),
                "warnings": meta["warnings"] + [f"Need at least {minimum} observed paired returns for block bootstrap"]}
    latest = frame.iloc[-1].to_dict()
    # Same row indexes for both legs preserve cross-leg and within-block temporal dependence.
    returns = frame[["price_a", "price_b"]].pct_change().dropna().to_numpy()
    simulations = min(10000, max(50, int(config.get("simulations", 500))))
    horizon = max(1, int(config.get("holding_days", 5)))
    entry_delay, exit_delay = max(1, int(config.get("execution_delay", 1))), max(0, int(config.get("exit_delay", 0)))
    path_horizon = min(126, horizon + entry_delay + exit_delay + 4)
    seed = int(config.get("seed", 42))
    block = max(1, min(int(config.get("block_length", 5)), len(returns)))
    boot = paired_block_bootstrap(returns, simulations, path_horizon, block, seed)
    pair = meta["pair"]
    specs = [get_spec(s, latest["date"], e, mode=config.get("mode", "real")) for s, e in zip(pair, (meta["expiry_a"], meta["expiry_b"]))]
    if any(s is None for s in specs):
        return {**meta, "status": "specification_unavailable", "scenarios": [], "cost_sensitivity": [], "sample_size": len(returns)}
    sizing = integer_hedge(specs[0], specs[1], latest["price_a"], latest["price_b"], float(config.get("capital", 10_000_000)), max_lots=int(config.get("max_lots", 100)))
    if not sizing.get("lots_a") or not sizing.get("lots_b"):
        return {**meta, "status": "no_feasible_integer_hedge", "scenarios": [], "cost_sensitivity": [], "sample_size": len(returns)}
    z = latest.get("zscore")
    signal = z if z is not None and pd.notna(z) else latest["normalized_spread"]
    side = -1 if signal > 0 else 1
    lots = np.array([abs(sizing["lots_a"]) * side, -abs(sizing["lots_b"]) * side], dtype=int)
    multiplier = np.array([s["trading_unit_g"] / s["quotation_unit_g"] for s in specs])
    units = np.array([s["trading_unit_g"] * s["purity"] / (1000 if s["purity"] > 1 else 1) for s in specs])
    prices = np.array([latest["price_a"], latest["price_b"]])
    gross_notional = float(np.sum(np.abs(lots) * multiplier * prices))
    common_vol = max(1e-6, float(np.std(returns.mean(axis=1))))
    residual_vol = max(1e-6, float(np.std(returns[:, 0] - returns[:, 1])))
    vol = float(config.get("volatility_stress", 1.0))
    costs, slip = float(config.get("cost_bps", 5)), float(config.get("slippage_bps", 2))
    if config.get('cost_schedule'):
        fees_config={**config,'slippage_bps':0}
        round_trip=sum(fill_cost(latest['date'],prices[i],int(sign*lots[i]),specs[i],fees_config) for i in (0,1) for sign in (1,-1))
        costs=round_trip/(2*gross_notional)*10000
        meta['warnings'].append('Counterfactual fees freeze the cutoff-date component schedule as an effective turnover rate; future fee-rule changes are not predicted.')
    classes = [
        {"name": "Base paired bootstrap"},
        {"name": "Increased transaction costs", "cost_multiplier": 3.0},
        {"name": "Execution slippage", "slippage_multiplier": 4.0},
        {"name": "Delayed entries", "entry_extra": 2},
        {"name": "Delayed exits", "exit_extra": 2},
        {"name": "Higher gold volatility", "vol_multiplier": 2.0},
        {"name": "Correlated adverse movements", "adverse_common": 2.0},
        {"name": "Residual spread expansion", "adverse_residual": 2.0},
        {"name": "Thin liquidity", "slippage_multiplier": 5.0, "liquidity_fraction": 0.25},
        {"name": "Contract expiry restrictions", "check_expiry": True},
        {"name": "Failed hedge execution", "failed_leg": "b", "unwind_after_sessions": 1,
         "slippage_multiplier": 5.0, "adverse_common": 2.0, "check_expiry": True},
        {"name": "Combined stress", "cost_multiplier": 3.0, "slippage_multiplier": 5.0, "entry_extra": 2, "exit_extra": 2, "vol_multiplier": 2.0, "adverse_residual": 2.0, "adverse_common": 2.0, "liquidity_fraction": 0.25, "check_expiry": True},
    ]
    scenarios, base_net, base_turnover = [], None, None
    for experiment in classes:
        scenario_lots = lots.copy()
        if experiment.get('failed_leg') == 'b':
            scenario_lots[1] = 0
        sampled = boot.copy()
        # Amplify the common gold factor; retain paired residual structure.
        common = sampled.mean(axis=2, keepdims=True)
        sampled += common * (vol * experiment.get("vol_multiplier", 1.0) - 1)
        residual_direction = np.array([-np.sign(lots[0]), -np.sign(lots[1])])
        sampled += residual_direction[None, None, :] * residual_vol * experiment.get("adverse_residual", 0) / np.sqrt(horizon)
        # A shared percentage return acts on signed MONEY notional. Fine grams
        # are appropriate for a shared absolute fine-gram price move instead.
        common_side = -np.sign(float(np.sum(scenario_lots * multiplier * prices)))
        sampled += common_side * common_vol * experiment.get("adverse_common", 0) / np.sqrt(horizon)
        sampled = np.clip(sampled, -0.95, 1.0)
        paths = np.concatenate([np.broadcast_to(prices, (simulations, 1, 2)), prices[None, None, :] * np.cumprod(1 + sampled, axis=1)], axis=1)
        entry = min(path_horizon - 1, entry_delay + experiment.get("entry_extra", 0))
        exit_index = min(path_horizon, entry + horizon + exit_delay + experiment.get("exit_extra", 0))
        if experiment.get('failed_leg'):
            exit_index = min(path_horizon, entry + experiment['unwind_after_sessions'])
        entry_prices, exit_prices = paths[:, entry, :], paths[:, exit_index, :]
        turnover = np.sum((entry_prices + exit_prices) * np.abs(scenario_lots) * multiplier, axis=1)
        gross = np.sum((exit_prices - entry_prices) * scenario_lots * multiplier, axis=1)
        net = gross - turnover * (costs * experiment.get("cost_multiplier", 1.0) + slip * experiment.get("slippage_multiplier", 1.0)) / 10_000
        expiry_ok = bool(latest["entry_eligible"])
        if experiment.get("check_expiry"):
            dates = [latest[f"lifecycle_{leg}"].get("tender_start") for leg in ("a", "b")]
            expiry_ok = expiry_ok and all(dates) and date.fromisoformat(latest["date"]) + timedelta(days=int(exit_index) * 2 + 2) < date.fromisoformat(min(dates))
        participation = max(abs(scenario_lots[0]) / max(1, float(latest["volume_a"] or 0)), abs(scenario_lots[1]) / max(1, float(latest["volume_b"] or 0)))
        liquidity_ok = participation <= float(config.get("max_participation", 0.01)) * experiment.get("liquidity_fraction", 1.0)
        scenarios.append({"name": experiment["name"], **_summary(net), "parameters": experiment, "entry_delay": entry, "exit_horizon": exit_index,
                          "position": {"lots_a": int(scenario_lots[0]), "lots_b": int(scenario_lots[1]),
                                       "residual_fine_g": float(np.sum(scenario_lots * units))},
                          "execution_assumption": ("First leg fills, second leg never fills; first leg is unwound one modeled session later with adverse gold move and increased slippage. No failure probability is estimated."
                                                   if experiment.get('failed_leg') else "Both legs follow the declared counterfactual fill delays; historical execution is unverified."),
                          "lifecycle_eligible": bool(expiry_ok), "liquidity_eligible": bool(liquidity_ok),
                          "status": "modeled_only" if expiry_ok and liquidity_ok else "financial_scenario_execution_blocked",
                          "worst_scenario_index": int(np.argmin(net)), "modeled_outcomes": net[:min(100, simulations)].tolist()})
        if base_net is None:
            base_net, base_turnover = net, turnover
    sensitivity = [{"cost_bps": c, **_summary(base_net - base_turnover * (c - costs) / 10_000)} for c in sorted(set([0.0, costs, costs * 2, costs * 4 + 1]))]
    correlation = float(np.corrcoef(returns.T)[0, 1]) if np.all(np.std(returns, axis=0) > 0) else None
    return clean_json({**meta, "status": "simulated", "as_of": latest["date"], "sample_size": len(returns), "simulations": simulations,
                       "seed": seed, "block_length": block, "horizon": horizon, "method": "circular moving-block bootstrap with jointly sampled paired returns",
                       "position": {"lots_a": int(lots[0]), "lots_b": int(lots[1]), "gross_notional": gross_notional, "residual_fine_g": float(np.sum(lots * units))},
                       "historical_return_correlation": correlation, "scenarios": scenarios, "cost_sensitivity": sensitivity,
                       "fragility": "fragile" if any(s["median_net_pnl"] <= 0 for s in scenarios) else "survives_modeled_medians",
                       "warnings": meta["warnings"] + ["Positive scenario rate is a simulated frequency, not a calibrated real-world probability of profit.",
                           "Close-to-close bootstrap prices are counterfactual research paths, not observed executable fills; position is diagnostic even without a defensible signal.",
                           "Adverse common-factor and residual shocks are explicit stress overlays; the empirical paired return blocks retain dependence.",
                           "Short histories give unstable tails; expected shortfall requires at least 200 simulations and is still uncalibrated."]})


def survival_map(df: pd.DataFrame, config: dict) -> dict:
    """Rerun exact historical fills for every cost/delay cell, no scaled profits."""
    costs = sorted(set([0.0, float(config.get("cost_bps", 5)), float(config.get("cost_bps", 5)) * 3 + 1]))
    delay = max(1, int(config.get("execution_delay", 1)))
    delays = [delay, delay + 1, delay + 2]
    cells = []
    for cost in costs:
        for entry_delay in delays:
            run = replay(df, {**config, "cost_bps": cost, "execution_delay": entry_delay, "cost_schedule": []})
            metrics = run["metrics"]
            cells.append({"cost_bps": cost, "execution_delay": entry_delay, "net_pnl": metrics["net_pnl"],
                          "gross_pnl": metrics["gross_pnl"], "trades": metrics["trades"], "max_drawdown": metrics["max_drawdown"],
                          "survives": metrics["trades"] > 0 and metrics["net_pnl"] > 0 and metrics.get('total_equity_change',metrics['net_pnl'])>0 and not run.get('open_position') and run.get("lifecycle_invariant_passed", False),
                          "evaluation_status":'not-evaluable' if run.get('open_position') else 'evaluated',
                          "unclosed_position": run.get("open_position") is not None})
    # One-dimensional slices expose other independent assumptions without an expensive Cartesian product.
    slices = []
    variants = [("exit_delay", int(config.get("exit_delay", 0)) + 2), ("slippage_bps", float(config.get("slippage_bps", 2)) * 3 + 1),
                ("min_volume", float(config.get("min_volume", 10)) * 5), ("holding_days", max(1, int(config.get("holding_days", 5)) * 2)),
                ("capital", float(config.get("capital", 10000000)) * .5),
                ("max_lots", max(1, int(config.get("max_lots", 100)) // 2))]
    for parameter, value in variants:
        run = replay(df, {**config, parameter: value})
        slices.append({"parameter": parameter, "value": value, **run["metrics"]})
    ghost = ghost_market(df, {**config, "simulations": min(300, int(config.get("simulations", 500)))})
    break_even = []
    for entry_delay in delays:
        same = [c for c in cells if c["execution_delay"] == entry_delay]
        positive = [c["cost_bps"] for c in same if c["survives"]]
        break_even.append({"execution_delay": entry_delay, "highest_tested_profitable_cost_bps": max(positive) if positive else None})
    # Exact zero-fee trade turnover gives a conditional linear break-even rate.
    # It is conditional because changes in costs can change policy decisions.
    zero=replay(df,{**config,'cost_bps':0,'slippage_bps':0,'cost_schedule':[]})
    turnover=sum(sum(float(part['turnover']) for part in trade.get(name,{}).values()) for trade in zero.get('trades',[]) for name in ('entry_cost_breakdown','exit_cost_breakdown'))
    break_even_total=zero['metrics']['gross_pnl']/turnover*10000 if turnover>0 and not zero.get('open_position') else None
    return {"mode": config.get("mode", "real"), "status": "evaluated" if any(c["trades"] for c in cells) else "no_eligible_trades",
            "cells": cells, "axes": {"cost_bps": costs, "execution_delay": delays}, "slices": slices,
            "volatility_and_liquidity_stresses": [{k: v for k, v in s.items() if k != "modeled_outcomes"} for s in ghost.get("scenarios", []) if s["name"] in ("Higher gold volatility", "Thin liquidity", "Contract expiry restrictions", "Failed hedge execution", "Combined stress")],
            "conditional_break_even_total_bps":break_even_total,
            "conditional_break_even_cost_bps":break_even_total-float(config.get('slippage_bps',2)) if break_even_total is not None else None,
            "conditional_break_even_slippage_bps":break_even_total-float(config.get('cost_bps',5)) if break_even_total is not None else None,
            "boundaries": break_even, "warnings": ["Every historical cell recomputes actual lot quantities, chronological signals and subsequent Open proxies.",
                "Capital and maximum-lot slices rerun integer hedge sizing; different quantities can change residual gold exposure and eligibility.",
                "Grid cells replace any detailed fee schedule with the displayed all-in bps assumption; slices retain the configured schedule. Break-even rates condition on the zero-cost trades and may be negative.",
                "Sensitivity cells reuse the same dataset; selecting the best cell is data snooping, not fresh out-of-sample validation.",
                "Volatility stress is counterfactual bootstrap output, separate from historical replay. Zero trades are not evidence that an opportunity survives."]}
