"""Historical feature similarity with outcomes completed strictly before cutoff."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .analytics import aligned_pair, clean_json


def find_analogs(df: pd.DataFrame, config: dict) -> dict:
    frame, meta = aligned_pair(df, config)
    horizon = max(1, int(config.get("holding_days", 5)))
    if frame.empty:
        return {**meta, "status": "insufficient_history", "analogs": [], "features": []}
    history = frame.copy().reset_index(drop=True)
    history["spread_change"] = history.residual.diff()
    history["volatility"] = history.gold_factor_return.rolling(max(3, int(config.get("window", 20)))).std()
    history["log_volume"] = np.log1p(history[["volume_a", "volume_b"]].min(axis=1).clip(lower=0))
    history['log_oi']=np.log1p(history[['oi_a','oi_b']].min(axis=1).clip(lower=0))
    history['residual_volatility']=history['std']
    history['trend_regime']=history.gold_factor_return.rolling(max(3,int(config.get('window',20)))).mean()
    history['deviation_persistence']=np.sign(history.residual-history.reference).rolling(max(3,int(config.get('window',20)))).mean()
    history["maturity_gap"] = history.days_to_expiry_b - history.days_to_expiry_a
    # Fixed feature definitions are chosen before examining the historical outcomes.
    feature_names = ["zscore", "robust_zscore", "spread_change", "volatility", "log_volume", "log_oi", "residual_volatility", "trend_regime", "deviation_persistence", "days_to_expiry_a", "maturity_gap"]
    query = history.iloc[-1]
    cutoff = str(query.date)
    if query[feature_names].isna().any():
        return {**meta, "status": "insufficient_query_features", "as_of": cutoff, "analogs": [], "features": feature_names}
    candidates = history.iloc[:max(0, len(history) - horizon - 1)].copy()
    candidates = candidates.dropna(subset=feature_names)
    if len(candidates) < 5:
        return {**meta, "status": "insufficient_completed_prior_outcomes", "as_of": cutoff, "analogs": [], "features": feature_names, "eligible_candidates": len(candidates)}
    # Fit the scaler only on prior completed candidates, never on query or later rows.
    matrix = candidates[feature_names].to_numpy(dtype=float)
    center = np.median(matrix, axis=0)
    scale = np.median(np.abs(matrix - center), axis=0) * 1.4826
    scale = np.where(scale > 1e-10, scale, np.std(matrix, axis=0))
    scale = np.where(scale > 1e-10, scale, 1.0)
    distances = np.sqrt(np.mean(((matrix - query[feature_names].to_numpy(dtype=float)) / scale) ** 2, axis=1))
    candidates["distance"] = distances
    selected, indexes = [], []
    for i, candidate in candidates.sort_values(["distance", "date"]).iterrows():
        if any(abs(int(i) - used) <= horizon for used in indexes):
            continue
        outcome = history.iloc[int(i) + horizon]
        if outcome.date >= cutoff:
            continue
        indexes.append(int(i))
        side = -1 if candidate.zscore > 0 else 1
        selected.append({"date": candidate.date, "outcome_date": outcome.date, "distance": candidate.distance,
                         "expiry_a": candidate.expiry_a, "expiry_b": candidate.expiry_b,
                         "feature_vector": {f: float(candidate[f]) for f in feature_names},
                         "residual_at_signal": candidate.residual, "residual_at_outcome": outcome.residual,
                         "signed_residual_change": side * (outcome.residual - candidate.residual),
                         "spread_narrowed": bool(side * (outcome.residual - candidate.residual) > 0),
                         "lifecycle_eligible_at_signal": bool(candidate.entry_eligible)})
        if len(selected) >= min(20, int(config.get("analog_count", 5))):
            break
    outcomes = [a["signed_residual_change"] for a in selected]
    return clean_json({**meta, "status": "matched" if selected else "insufficient_history", "as_of": cutoff, "horizon": horizon,
                       "features": feature_names, "query_features": {f: float(query[f]) for f in feature_names},
                       "eligible_candidates": len(candidates), "analogs": selected,
                       "scaler": {"fit_end": str(candidates.date.max()), "center": center.tolist(), "scale": scale.tolist(), "method": "prior-candidate robust median/MAD, standard-deviation fallback"},
                       "outcome_summary": {"sample_size": len(selected), "median_signed_residual_change": float(np.median(outcomes)) if outcomes else None,
                                           "narrowing_frequency": sum(x > 0 for x in outcomes) / len(outcomes) if outcomes else None},
                       "warnings": meta["warnings"] + ["Analog outcomes are descriptive normalized spread changes, not executable profit forecasts.",
                          "All candidate outcome dates are strictly earlier than the query cutoff; overlapping analog horizons are suppressed.",
                          "Similarity is not causal equivalence or calibrated predictive probability; the available exact-contract history can be short."]})
