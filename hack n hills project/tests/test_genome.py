from copy import deepcopy

import pytest

from backend.services.genome import get_spec, integer_hedge, lifecycle, list_specs, normalize, select_spec


def spec(symbol="GOLDM"):
    return get_spec(symbol, "2026-01-05", "2026-05-05", mode="synthetic")


def test_lot_size_does_not_replace_quotation_size():
    result = normalize(100000, spec())
    assert result["quotation_normalized"] == 10000
    assert result["purity_adjusted"] == pytest.approx(10000 / .995)
    assert result["lot_value"] == 1000000
    assert result["fine_grams_per_lot"] == 99.5


def test_purity_conversion_is_consistent_across_instruments():
    fine_price = 10000
    mini = normalize(fine_price * .995 * 10, spec("GOLDM"))
    ten = normalize(fine_price * .999 * 10, spec("GOLDTEN"))
    petal = normalize(fine_price * .999, spec("GOLDPETAL"))
    assert mini["purity_adjusted"] == pytest.approx(ten["purity_adjusted"])
    assert petal["purity_adjusted"] == pytest.approx(ten["purity_adjusted"])


def test_real_rule_change_selected_by_contract_expiry_not_trade_date():
    old = get_spec("GOLDTEN", "2025-09-15", "2025-10-31")
    new = get_spec("GOLDTEN", "2025-09-15", "2025-11-28")
    assert old["tender_days"] == 5
    assert new["tender_days"] == 3
    assert old["spec_id"] != new["spec_id"]
    assert not old["verified"] and not new["verified"]


def test_spec_registry_preserves_geographical_basis():
    assert get_spec("GOLDPETAL", "2026-05-01", "2026-07-31")["quote_location"] == "Mumbai"
    assert get_spec("GOLDTEN", "2026-05-01", "2026-07-31")["quote_location"] == "Ahmedabad"


def test_no_expiry_yields_only_unverified_baseline_and_no_early_goldten():
    assert not get_spec("GOLDM", "2026-05-01")["verified"]
    assert get_spec("GOLDTEN", "2024-01-01", "2024-04-30") is None


def test_no_official_evidence_is_inferred_from_synthetic_specs():
    assert all(s["mode"] == "real" and not s["verified"] for s in list_specs())
    assert all(s["mode"] == "synthetic" for s in list_specs("synthetic"))


def test_historical_boundaries_inclusive_and_no_future_version():
    before = get_spec("GOLDM", "2026-01-01", "2026-04-05")
    after = get_spec("GOLDM", "2026-01-01", "2026-05-05")
    assert before["effective_from"] == "2025-11-01"
    assert after["effective_from"] == "2026-05-01"
    before["tender_days"] = 99
    assert get_spec("GOLDM", "2026-01-01", "2026-04-05")["tender_days"] == 3


def test_unknown_real_calendar_blocks_execution():
    row = {"symbol": "GOLDM", "date": "2026-04-01", "expiry": "2026-05-05", "mode": "real"}
    outcome = lifecycle(row)
    assert not outcome["entry_eligible"]
    assert outcome["tender_start"] is None
    assert any("calendar" in reason for reason in outcome["reasons"])


def test_verified_calendar_would_allow_only_before_tender():
    fixture = {**spec(), "mode": "real"}
    row = {"symbol": "GOLDM", "date": "2026-05-01", "expiry": "2026-05-05", "mode": "real",
           "calendar_verified": True, "tender_start": "2026-05-01", "listing_date": "2025-11-06"}
    assert not lifecycle(row, fixture)["entry_eligible"]
    row["date"] = "2026-04-30"
    assert lifecycle(row, fixture)["entry_eligible"]
    row["date"] = "2025-11-05"
    assert not lifecycle(row, fixture)["entry_eligible"]


def test_synthetic_lifecycle_and_expired_contract():
    row = {"symbol": "GOLDM", "date": "2026-05-01", "expiry": "2026-05-05", "mode": "synthetic"}
    outcome = lifecycle(row)
    assert outcome["entry_eligible"] and outcome["exit_eligible"]
    assert outcome["execution_status"] == "hypothetical_synthetic"
    assert outcome["tender_start"] == "2026-05-03"
    row["date"] = "2026-05-06"
    assert not lifecycle(row)["entry_eligible"]
    assert not lifecycle(row)["exit_eligible"]


def test_spec_mode_mismatch_blocks_execution():
    row = {"symbol": "GOLDM", "date": "2026-04-01", "expiry": "2026-05-05", "mode": "real"}
    outcome = lifecycle(row, spec())
    assert any("modes" in reason for reason in outcome["reasons"])


def test_integer_sizing_respects_gross_capital_and_purity():
    outcome = integer_hedge(spec("GOLDM"), spec("GOLDTEN"), 99500, 99900, 2_000_000)
    assert outcome["eligible"]
    assert outcome["lots_a"] == 1 and outcome["lots_b"] == 10
    assert outcome["fine_grams_residual"] == pytest.approx(-.4)
    assert outcome["notional"] == 1_994_000
    assert not outcome["exact_metal_neutral"]


def test_unaffordable_pair_does_not_return_fractional_or_zero_leg_trade():
    outcome = integer_hedge(spec("GOLDM"), spec("GOLDTEN"), 100000, 100000, 1000)
    assert not outcome["eligible"]
    assert outcome["lots_a"] == outcome["lots_b"] == 0


def test_same_purity_contracts_can_be_exactly_metal_matched():
    outcome = integer_hedge(spec("GOLDTEN"), spec("GOLDPETAL"), 100000, 10000, 300000)
    assert outcome["lots_a"] == 1 and outcome["lots_b"] == 10
    assert outcome["exact_metal_neutral"]


@pytest.mark.parametrize("price", [0, -1, float("nan"), float("inf")])
def test_invalid_normalization_price_raises(price):
    with pytest.raises(ValueError):
        normalize(price, spec())
