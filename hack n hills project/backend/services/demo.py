"""Isolated deterministic demonstration, never represented as MCX history."""
import numpy as np
import pandas as pd
from .genome import get_spec

LABEL = "SYNTHETIC DEMONSTRATION — NOT ACTUAL MCX PERFORMANCE"


def demo_csv(seed=42):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2025-01-02", periods=180)
    gold = 9000 + np.cumsum(rng.normal(1, 19, len(dates)))
    residual = np.zeros(len(dates))
    for i in range(1, len(dates)):
        residual[i] = 0.70 * residual[i-1] + rng.normal(0, 5)
    # Planted temporary departures and one adverse, persistent widening.
    for i in [32, 61, 92, 122, 151]:
        residual[i:i+7] += np.array([85, 75, 50, 30, 15, 5, 0])
    residual[164:174] -= np.linspace(20, 100, 10)
    rows = []
    for j, symbol in enumerate(("GOLDM", "GOLDTEN", "GOLDGUINEA", "GOLDPETAL")):
        for expiry in ["2025-10-31", "2025-12-31", "2026-02-27"]:
            previous = None
            for i, day in enumerate(dates):
                spec = get_spec(symbol, day.date().isoformat(), expiry, mode="synthetic")
                dte = (pd.Timestamp(expiry)-day).days
                fine = gold[i] + dte * 0.35 + (residual[i] if j == 0 else rng.normal(0, 2)) + j * 2
                close = fine * spec["quotation_unit_g"] * spec["purity"]
                op = (previous if previous is not None else close) + rng.normal(0, 2) * spec["quotation_unit_g"]
                high, low = max(op, close)*1.001, min(op, close)*0.999
                rows.append({"Symbol": symbol, "Instrument": "FUTCOM", "Date": day.date().isoformat(),
                             "ExpiryDate": expiry, "Open": round(op, 4), "High": round(high, 4), "Low": round(low, 4),
                             "Close": round(close, 4), "Volume": 25000 if i % 47 else 8, "OpenInterest": 18000})
                previous = close
    return pd.DataFrame(rows).to_csv(index=False).encode("utf-8")


def create_demo(storage, seed=42):
    report = storage.import_bytes(f"synthetic_seed_{seed}.csv", demo_csv(seed), mode="synthetic")
    return {"label": LABEL, "seed": seed, "import": report, "summary": storage.summary("synthetic"),
            "planted_conditions": ["Common gold factor", "Dependent leg moves", "Temporary residual shocks",
                                   "Adverse persistent widening", "Thin-liquidity sessions", "Three synthetic expiries per product"],
            "calendar": "Business weekdays are a synthetic model calendar; not MCX holidays."}
