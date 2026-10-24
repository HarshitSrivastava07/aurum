import pytest

from backend.services.replay import replay
from tests.test_financial import CONFIG, market_fixture


def test_next_session_exact_contracts_and_accounting():
    result = replay(market_fixture(), CONFIG)
    assert result["trades"], "Fixture must actually exercise execution and P&L"
    for trade in result["trades"]:
        assert trade["signal_date"] < trade["entry_date"] < trade["exit_date"]
        assert trade["expiry_a"] == trade["expiry_b"] == "2025-12-31"
        assert isinstance(trade["lots_a"], int) and isinstance(trade["lots_b"], int)
        assert trade["gross_pnl"] == pytest.approx(trade["leg_a_pnl"] + trade["leg_b_pnl"])
        assert trade["net_pnl"] == pytest.approx(trade["gross_pnl"] - trade["costs"])
        assert trade["gross_pnl"] == pytest.approx(trade["gold_factor_contribution"] + trade["relative_value_contribution"])
    assert result["walk_forward"]
    assert result["holdout"]["status"] == "evaluated_frozen_parameters"
    assert not result["execution_validated"]


def test_same_day_settlement_fill_is_rejected():
    with pytest.raises(ValueError, match="at least one"):
        replay(market_fixture(), {**CONFIG, "execution_delay": 0})


def test_future_mutation_cannot_change_cutoff_replay():
    frame = market_fixture()
    config = {**CONFIG, "cutoff": "2025-04-03"}
    original = replay(frame, config)
    frame.loc[frame.date > config["cutoff"], ["open", "close"]] *= 50
    assert replay(frame, config) == original


def test_holdout_price_mutation_does_not_refit_parameters():
    frame = market_fixture()
    original = replay(frame, CONFIG)
    start = original["holdout"]["start"]
    frame.loc[frame.date >= start, ["open", "close"]] *= 1.3
    mutated = replay(frame, CONFIG)
    assert mutated["holdout"]["training_hash"] == original["holdout"]["training_hash"]
    assert mutated["holdout"]["frozen_threshold"] == original["holdout"]["frozen_threshold"]
    assert mutated["walk_forward"] == original["walk_forward"]
    assert mutated["holdout"]["snapshot_hash"] != original["holdout"]["snapshot_hash"]


def test_automatic_selection_does_not_use_future_contract_overlap():
    frame = market_fixture()
    future = frame.loc[frame.date >= "2025-03-03"].copy()
    future["expiry"] = "2026-12-31"
    import pandas as pd
    result = replay(pd.concat([frame, future], ignore_index=True), CONFIG)
    assert result["expiry_a"] == result["expiry_b"] == "2025-12-31"


def test_unverified_lifecycle_blocks_entries():
    frame = market_fixture()
    frame["mode"] = "real"
    result = replay(frame, {**CONFIG, "mode": "real"})
    assert result["trades"] == []
    assert not result["execution_validated"]


def test_missing_open_does_not_substitute_close():
    frame = market_fixture()
    frame["open"] = None
    result = replay(frame, CONFIG)
    assert result["trades"] == []
    assert any("Missing genuine Open" in e.get("reason", "") for e in result["events"])


def test_replay_decision_prefix_is_stable_when_cutoff_advances():
    frame=market_fixture()
    cfg={**CONFIG,'start':frame.date.min(),'end':frame.date.max(),'cutoff':'2025-03-20'}
    early=replay(frame,cfg)
    late=replay(frame,{**cfg,'cutoff':frame.date.max()})
    assert early['events']==[e for e in late['events'] if e['date']<=cfg['cutoff']]
    assert early['equity']==[e for e in late['equity'] if e['date']<=cfg['cutoff']]
    assert early['holdout']['planned_boundary']==late['holdout']['planned_boundary']
