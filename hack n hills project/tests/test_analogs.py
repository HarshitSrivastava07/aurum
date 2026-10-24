from backend.services.analogs import find_analogs
from tests.test_financial import CONFIG, market_fixture


def test_analogs_finish_outcomes_before_query_cutoff():
    result = find_analogs(market_fixture(), CONFIG)
    assert result["analogs"]
    for analog in result["analogs"]:
        assert analog["date"] < analog["outcome_date"] < result["as_of"]
        assert analog["expiry_a"] == analog["expiry_b"] == "2025-12-31"
    assert result["scaler"]["fit_end"] < result["as_of"]


def test_future_analogs_and_future_outcomes_cannot_leak():
    frame = market_fixture()
    config = {**CONFIG, "cutoff": "2025-04-03"}
    original = find_analogs(frame, config)
    frame.loc[frame.date > config["cutoff"], ["open", "close"]] *= 100
    assert find_analogs(frame, config) == original


def test_short_history_reports_insufficiency():
    result = find_analogs(market_fixture(5), CONFIG)
    assert result["status"] == "insufficient_query_features"
    assert result["analogs"] == []
