"""Independent money/unit examples and empirical curve behavior."""
import math

import numpy as np
import pandas as pd
import pytest

from backend.services.analytics import analyze_pair, curve_analysis
from backend.services.genome import normalize, integer_hedge
from backend.services.replay import leg_pnl, trade_cost


MINI = {"trading_unit_g": 100, "quotation_unit_g": 10, "purity": 0.995}
TEN = {"trading_unit_g": 10, "quotation_unit_g": 10, "purity": 0.999}


def market_fixture(n=120):
    """Explicitly synthetic two-contract prices, independent of production generators."""
    rows = []
    for i, day in enumerate(pd.bdate_range("2025-01-02", periods=n)):
        base = 10000 + i * 2 + 20 * math.sin(i / 11)
        spread = 15 * math.sin(i / 3) + (100 if i % 17 == 12 else 0)
        for symbol, spec, fine in [("GOLDM", MINI, base + spread), ("GOLDTEN", TEN, base)]:
            price = fine * spec["quotation_unit_g"] * spec["purity"]
            rows.append({"date": day.date().isoformat(), "expiry": "2025-12-31", "symbol": symbol, "instrument": "FUTCOM",
                         "open": price * (1 + 0.00005 * math.sin(i)), "close": price, "settlement": None,
                         "high": price * 1.01, "low": price * 0.99, "volume": 20000, "open_interest": 10000,
                         "mode": "synthetic", "validation_status": "valid", "source_hash": "synthetic-independent-financial-fixture"})
    return pd.DataFrame(rows)


CONFIG = {"mode": "synthetic", "pair": ["GOLDM", "GOLDTEN"], "window": 10, "z_threshold": 1.5,
          "capital": 10_000_000, "max_lots": 100, "holding_days": 3, "cost_bps": 1, "slippage_bps": 0,
          "execution_delay": 1, "simulations": 200, "seed": 42}


def test_normalization_independent_fine_gram_example():
    result = normalize(99500, MINI)
    assert result["quotation_normalized"] == 9950
    assert result["purity_adjusted"] == 10000
    assert result["lot_value"] == 995000
    assert normalize(99900, TEN)["purity_adjusted"] == 10000


def test_actual_contract_money_and_long_short_pnl():
    assert leg_pnl(100000, 100100, 2, MINI) == 2000
    assert leg_pnl(100000, 100100, -10, TEN) == -1000
    assert trade_cost(100000, 100100, 2, MINI, 7) == pytest.approx(2801.4)
    assert 2000 - trade_cost(100000, 100100, 2, MINI, 7) == pytest.approx(-801.4)
    with pytest.raises(ValueError, match="integers"):
        leg_pnl(100000, 100100, 1.5, MINI)


def test_integer_hedge_exposes_fine_metal_mismatch():
    hedge = integer_hedge(MINI, TEN, 99500, 99900, 2_000_000, max_lots=10)
    assert (hedge["lots_a"], hedge["lots_b"]) == (1, 10)
    assert hedge["gross_notional"] == 1_994_000
    assert hedge["residual_fine_g"] == pytest.approx(-0.4)
    assert not hedge["exact_metal_neutral"]


def test_shifted_reference_does_not_fit_current_shock():
    result = analyze_pair(market_fixture(40), CONFIG)
    series = result["series"]
    index = 29
    past = [r["residual"] for r in series[index - 10:index]]
    assert series[index]["reference"] == pytest.approx(np.mean(past))
    assert series[index]["std"] == pytest.approx(np.std(past, ddof=1))
    assert series[9]["zscore"] is None
    assert series[10]["zscore"] is not None


def test_curve_interpolation_decomposition_and_no_extrapolation():
    rows = []
    for day, shift in [("2025-01-02", 0), ("2025-01-03", 4)]:
        for expiry in ["2025-03-31", "2025-06-30", "2025-09-30"]:
            dt = (pd.Timestamp(expiry) - pd.Timestamp(day)).days
            fine = 10000 + 2 * dt + shift
            rows.append({"symbol": "GOLDM", "date": day, "expiry": expiry, "close": fine * 9.95, "mode": "synthetic", "validation_status": "valid"})
    result = curve_analysis(pd.DataFrame(rows), "2025-01-03", "GOLDM")
    assert result["classification"] == "contango"
    assert result["calendar_spreads"][0]["inr_per_fine_g_per_day"] == pytest.approx(2)
    assert result["decomposition"][0]["mechanical_roll_down"] is None  # just outside previous curve
    assert result["decomposition"][1]["mechanical_roll_down"] == pytest.approx(-2)
    assert result["decomposition"][1]["residual_curve_shift"] == pytest.approx(4)


def test_future_cutoff_and_mode_separation():
    frame = market_fixture(60)
    cutoff = "2025-02-20"
    before = analyze_pair(frame, {**CONFIG, "cutoff": cutoff})
    frame.loc[frame.date > cutoff, "close"] *= 99
    assert analyze_pair(frame, {**CONFIG, "cutoff": cutoff}) == before
    frame.loc[0, "mode"] = "real"
    with pytest.raises(ValueError, match="separated"):
        analyze_pair(frame, CONFIG)
