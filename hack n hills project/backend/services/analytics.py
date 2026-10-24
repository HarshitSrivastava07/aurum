"""Point-in-time relative value in INR per fine gram, with exact contracts."""
from __future__ import annotations

from itertools import combinations
import math
from typing import Any

import numpy as np
import pandas as pd

from .genome import get_spec, normalize, lifecycle


SYMBOLS = ("GOLDM", "GOLDTEN", "GOLDGUINEA", "GOLDPETAL")


def clean_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): clean_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean_json(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return float(value) if math.isfinite(value) else None
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (pd.Timestamp,)):
        return value.date().isoformat()
    return value


def prepare(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Filter before any estimator can inspect rows beyond the information cutoff."""
    data = df.copy()
    if data.empty:
        return data
    mode = config.get("mode", "real")
    if "mode" not in data:
        raise ValueError("Every observation must declare real or synthetic mode")
    if set(data["mode"].dropna().unique()) != {mode} or data["mode"].isna().any():
        raise ValueError("Real and synthetic data must be separated before analysis")
    for name in ("date", "expiry"):
        data[name] = pd.to_datetime(data[name], errors="raise").dt.strftime("%Y-%m-%d")
    limit = min(str(v)[:10] for v in [config.get("end"), config.get("cutoff")] if v) if (config.get("end") or config.get("cutoff")) else None
    if limit:
        data = data.loc[data["date"] <= limit]
    if "validation_status" in data:
        data = data.loc[~data["validation_status"].astype(str).str.lower().isin(["invalid", "rejected", "quarantined"])]
    data = data.loc[data["date"] <= data["expiry"]]
    if data.duplicated(["symbol", "date", "expiry"]).any():
        raise ValueError("Duplicate contract sessions require ingestion reconciliation")
    return data.sort_values(["date", "symbol", "expiry"]).reset_index(drop=True)


def _price(row: dict) -> tuple[float | None, str]:
    # Close is never relabelled as final settlement.
    for key in ("close", "settlement"):
        val = row.get(key)
        if val is not None and pd.notna(val) and np.isfinite(float(val)) and float(val) > 0:
            return float(val), key
    return None, "unavailable"


def choose_contracts(data: pd.DataFrame, config: dict) -> tuple[str | None, str | None]:
    pair = config.get("pair", ["GOLDM", "GOLDTEN"])
    if len(pair) != 2 or pair[0] == pair[1] or any(s not in SYMBOLS for s in pair):
        raise ValueError("Choose two different supported gold products")
    a, b = (data.loc[data["symbol"] == s] for s in pair)
    ea, eb = config.get("expiry_a"), config.get("expiry_b")
    if ea:
        a = a.loc[a["expiry"] == ea]
    if eb:
        b = b.loc[b["expiry"] == eb]
    overlap = a[["date", "expiry"]].merge(b[["date", "expiry"]], on="date", suffixes=("_a", "_b"))
    if overlap.empty:
        return ea, eb
    counts = overlap.groupby(["expiry_a", "expiry_b"]).size().reset_index(name="sessions")
    chosen = counts.sort_values(["sessions", "expiry_a", "expiry_b"], ascending=[False, True, True]).iloc[0]
    return str(chosen.expiry_a), str(chosen.expiry_b)


def _curve_points(data: pd.DataFrame, date: str, symbol: str, mode: str) -> list[dict]:
    points = []
    for row in data.loc[(data["date"] == date) & (data["symbol"] == symbol)].to_dict("records"):
        spec = get_spec(symbol, date, row["expiry"], mode=mode)
        price, field = _price(row)
        if spec is None or price is None:
            continue
        points.append({"expiry": row["expiry"], "days_to_expiry": (pd.Timestamp(row["expiry"]) - pd.Timestamp(date)).days,
                       "price": price, "price_field": field, "fine_price": normalize(price, spec)["purity_adjusted"], "spec_id": spec.get("spec_id")})
    return sorted(points, key=lambda p: p["days_to_expiry"])


def _interpolate(points: list[dict], target_days: float) -> float | None:
    if len(points) < 2:
        return None
    xs = [p["days_to_expiry"] for p in points]
    if target_days < min(xs) or target_days > max(xs):
        return None
    return float(np.interp(target_days, xs, [p["fine_price"] for p in points]))


def aligned_pair(df: pd.DataFrame, config: dict) -> tuple[pd.DataFrame, dict]:
    data = prepare(df, config)
    pair = config.get("pair", ["GOLDM", "GOLDTEN"])
    metadata = {"pair": pair, "mode": config.get("mode", "real"), "warnings": [], "unit": "INR per fine gram"}
    if data.empty:
        return pd.DataFrame(), {**metadata, "warnings": ["No eligible observations available"]}
    ea, eb = choose_contracts(data, config)
    metadata.update(expiry_a=ea, expiry_b=eb, selection="explicit expiries" if config.get("expiry_a") and config.get("expiry_b") else "greatest overlap within information cutoff; one fixed contract per leg")
    a = data.loc[(data.symbol == pair[0]) & (data.expiry == ea)]
    b = data.loc[(data.symbol == pair[1]) & (data.expiry == eb)]
    merged = a.merge(b, on="date", suffixes=("_a", "_b"))
    rows = []
    for combined in merged.to_dict("records"):
        day = combined["date"]
        ra = {k[:-2]: v for k, v in combined.items() if k.endswith("_a")}
        rb = {k[:-2]: v for k, v in combined.items() if k.endswith("_b")}
        ra["date"], rb["date"] = day, day
        specs = [get_spec(s, day, e, mode=metadata["mode"]) for s, e in zip(pair, (ea, eb))]
        if any(s is None for s in specs):
            metadata["warnings"].append("Missing date-effective specification; affected rows excluded")
            continue
        pa, fa = _price(ra)
        pb, fb = _price(rb)
        if pa is None or pb is None:
            continue
        na, nb = normalize(pa, specs[0]), normalize(pb, specs[1])
        dta, dtb = ((pd.Timestamp(e) - pd.Timestamp(day)).days for e in (ea, eb))
        spread = na["purity_adjusted"] - nb["purity_adjusted"]
        maturity = 0.0 if ea == eb else None
        if maturity is None:
            points = _curve_points(data, day, pair[0], metadata["mode"])
            target = _interpolate(points, dtb)
            if target is not None:
                maturity = na["purity_adjusted"] - target
        la, lb = lifecycle(ra, specs[0]), lifecycle(rb, specs[1])
        rows.append({"date": day, "expiry_a": ea, "expiry_b": eb, "price_a": pa, "price_b": pb,
                     "price_field_a": fa, "price_field_b": fb,
                     "raw_spread": pa - pb, "quotation_spread": na["quotation_normalized"] - nb["quotation_normalized"],
                     "normalized_a": na["purity_adjusted"], "normalized_b": nb["purity_adjusted"],
                     "normalized_spread": spread, "maturity_component": maturity, "maturity_adjusted": maturity is not None,
                     "residual": spread if config.get("baseline") == "A" else spread - (maturity or 0), "days_to_expiry_a": dta, "days_to_expiry_b": dtb,
                     "open_a": ra.get("open"), "open_b": rb.get("open"),
                     "volume_a": ra.get("volume"), "volume_b": rb.get("volume"),
                     "oi_a": ra.get("open_interest"), "oi_b": rb.get("open_interest"),
                     "entry_eligible": bool(la.get("entry_eligible") and lb.get("entry_eligible")),
                     "lifecycle_a": la, "lifecycle_b": lb,
                     "spec_id_a": specs[0].get("spec_id"), "spec_id_b": specs[1].get("spec_id"),
                     "spec_verified": bool(specs[0].get("verified") and specs[1].get("verified")),
                     "basis_risk": specs[0].get("quote_location") != specs[1].get("quote_location") or not specs[0].get("quote_location")})
    frame = pd.DataFrame(rows)
    if frame.empty:
        metadata["warnings"].append("No overlapping sessions for selected exact contracts")
        return frame, metadata
    window = max(3, int(config.get("window", 20)))
    # shift BEFORE all fitted statistics: today's shock never trains today's reference.
    history = frame.residual.shift(1)
    frame["reference"] = history.rolling(window, min_periods=window).mean()
    frame["std"] = history.rolling(window, min_periods=window).std(ddof=1)
    frame["median"] = history.rolling(window, min_periods=window).median()
    frame["mad"] = history.rolling(window, min_periods=window).apply(lambda x: float(np.median(np.abs(x - np.median(x)))), raw=True)
    frame["zscore"] = (frame.residual - frame.reference) / frame["std"].replace(0, np.nan)
    frame["robust_zscore"] = (frame.residual - frame["median"]) / (1.4826 * frame["mad"].replace(0, np.nan))
    frame["gold_factor_return"] = ((frame.normalized_a.pct_change(fill_method=None) + frame.normalized_b.pct_change(fill_method=None)) / 2)
    frame["factor_price"] = (frame.normalized_a + frame.normalized_b) / 2
    frame["liquid"] = (frame[["volume_a", "volume_b"]].fillna(-1) >= float(config.get("min_volume", 10))).all(axis=1) & (frame[["oi_a", "oi_b"]].fillna(-1) >= float(config.get("min_oi", 10))).all(axis=1)
    frame["candidate"] = (frame.zscore.abs() >= float(config.get("z_threshold", 2))) & frame.liquid & frame.entry_eligible
    if not frame.maturity_adjusted.all():
        metadata["warnings"].append("Insufficient bracketing same-product curve: some residuals retain unresolved maturity basis; no extrapolation or theoretical fair value")
    if frame.basis_risk.any():
        metadata["warnings"].append("Different or unknown quotation locations: geographic basis remains unresolved")
    if not frame.spec_verified.all():
        metadata["warnings"].append("Unverified historical specifications prevent valid execution claims")
    metadata["warnings"].append("Rolling deviations are descriptive; mean reversion and executable arbitrage have not been established")
    metadata["warnings"] = sorted(set(metadata["warnings"]))
    return frame, metadata


def analyze_pair(df: pd.DataFrame, config: dict) -> dict:
    frame, meta = aligned_pair(df, config)
    if config.get("start") and not frame.empty:
        frame = frame.loc[frame.date >= str(config["start"])]
    latest = frame.iloc[-1].to_dict() if not frame.empty else None
    return clean_json({**meta, "series": frame.to_dict("records"), "latest": latest, "sessions": len(frame),
                       "status": "candidate_requires_falsification" if latest and latest["candidate"] else "no_opportunity",
                       "message": "Statistical deviation identified; investigate contractual and execution risks." if latest and latest["candidate"] else "No meaningful opportunity identified under the selected assumptions."})


def compare_all_pairs(df: pd.DataFrame, config: dict) -> list[dict]:
    return [analyze_pair(df, {**config, "pair": list(pair), "expiry_a": None, "expiry_b": None}) for pair in combinations(SYMBOLS, 2)]


def curve_analysis(df: pd.DataFrame, as_of: str, symbol: str) -> dict:
    mode = str(df["mode"].iloc[0]) if not df.empty and "mode" in df else "real"
    data = prepare(df, {"mode": mode, "cutoff": as_of})
    points = _curve_points(data, as_of, symbol, mode) if not data.empty else []
    spreads = []
    for a, b in zip(points, points[1:]):
        gap = b["days_to_expiry"] - a["days_to_expiry"]
        slope = (b["fine_price"] - a["fine_price"]) / gap if gap else None
        spreads.append({"near_expiry": a["expiry"], "far_expiry": b["expiry"], "calendar_spread": b["fine_price"] - a["fine_price"],
                        "maturity_days": gap, "inr_per_fine_g_per_day": slope,
                        "annualized_curve_ratio": ((b["fine_price"] / a["fine_price"]) - 1) * 365 / gap if gap else None})
    previous_dates = sorted(data.loc[(data.symbol == symbol) & (data.date < as_of), "date"].unique()) if not data.empty else []
    decomposition = []
    if previous_dates:
        prev_date = previous_dates[-1]
        previous = _curve_points(data, prev_date, symbol, mode)
        for current in points:
            prior = next((x for x in previous if x["expiry"] == current["expiry"]), None)
            if prior is None:
                continue
            rolled = _interpolate(previous, current["days_to_expiry"])
            change = current["fine_price"] - prior["fine_price"]
            roll_down = rolled - prior["fine_price"] if rolled is not None else None
            decomposition.append({"expiry": current["expiry"], "previous_date": prev_date, "unchanged_contract_change": change,
                                  "mechanical_roll_down": roll_down, "residual_curve_shift": change - roll_down if roll_down is not None else None,
                                  "contract_switch_component": 0.0})
    signs = [np.sign(s["calendar_spread"]) for s in spreads]
    shape = "insufficient_curve" if not signs else "contango" if all(s > 0 for s in signs) else "backwardation" if all(s < 0 for s in signs) else "flat" if all(s == 0 for s in signs) else "mixed"
    return clean_json({"as_of": as_of, "symbol": symbol, "mode": mode, "points": points, "calendar_spreads": spreads,
                       "classification": shape, "decomposition": decomposition,
                       "model": "piecewise linear empirical curve; interpolation only, no extrapolation",
                       "warnings": ["Curve-relative estimates are not theoretical fair value: rates, storage and delivery basis are unavailable.",
                                    "Roll-down is a modeled movement along the prior curve for an unchanged contract; no synthetic return across expiry switches."]})
