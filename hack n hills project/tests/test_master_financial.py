"""Independent known answers and adverse counterexamples for the master audit.

All prices here are hypothetical test fixtures, never actual MCX observations.
"""
from decimal import Decimal
import math

import numpy as np
import pandas as pd
import pytest

from backend.services.analytics import analyze_pair
from backend.services.education import compare_hypothetical_quotes
from backend.services.genome import normalize
from backend.services.red_team import audit
from backend.services.replay import leg_pnl, replay
from backend.services.scenarios import ghost_market, paired_block_bootstrap, survival_map
from backend.services.storage import Storage
from tests.test_financial import CONFIG, MINI, TEN, market_fixture


def test_one_goldm_lot_known_money_answer_is_fifty_thousand():
    # 100g lot / 10g quote = 10 quotation units, independent of purity.
    assert leg_pnl(100000, 105000, 1, MINI) == 50000
    assert leg_pnl(100000, 105000, -1, MINI) == -50000
    assert leg_pnl(100000, 105000, 1, TEN) == 5000


def test_normalization_known_answer_uses_common_999_basis():
    adjusted = Decimal(100000) * Decimal(999) / Decimal(995)
    difference = Decimal(101000) - adjusted
    assert float(adjusted) == pytest.approx(100402.01005025125, abs=1e-8)
    assert float(difference) == pytest.approx(597.9899497487437, abs=1e-8)
    assert normalize(100000, MINI)["purity_adjusted"] * 9.99 == pytest.approx(float(adjusted))
    example = compare_hypothetical_quotes(100000, 101000)
    assert example["goldm"]["original_per_10g"] == 100000
    assert example["goldm"]["purity_adjusted_per_10g"] == pytest.approx(float(adjusted))
    assert example["goldten"]["purity_adjusted_per_10g"] == pytest.approx(101000)
    assert example["difference"] == pytest.approx(float(difference))
    assert example["raw_difference_per_10g"] == 1000
    assert example["status"] == "hypothetical_education"
    assert "HYPOTHETICAL" in example["provenance"]
    assert any("not an arbitrage" in text for text in example["limitations"])


@pytest.mark.parametrize("quote", [0, -1, float("nan"), float("inf")])
def test_educational_quote_input_cannot_produce_invalid_prices(quote):
    with pytest.raises(ValueError):
        compare_hypothetical_quotes(quote, 101000)


def test_benchmarks_apply_dated_component_fees_instead_of_aggregate_bps():
    frame = market_fixture(45)
    config = {**CONFIG, "cost_bps": 0, "slippage_bps": 0, "cost_schedule": [
        {"schedule_id": "early", "effective_from": "2025-01-01", "effective_to": "2025-01-31", "brokerage_per_lot": 11},
        {"schedule_id": "late", "effective_from": "2025-02-01", "brokerage_per_lot": 29},
    ]}
    run = replay(frame, config)
    directional, pair = run["baselines"][1:]
    first = frame.loc[frame.symbol == "GOLDM"].iloc[0]
    last = frame.loc[frame.symbol == "GOLDM"].iloc[-1]
    gross = (last.close - first.open) * directional["lots"] * 10
    assert directional["net_pnl"] == pytest.approx(gross - directional["lots"] * (11 + 29))
    assert pair["costs"] == pytest.approx((abs(pair["lots_a"]) + abs(pair["lots_b"])) * (11 + 29))
    assert directional["status"] == pair["status"] == "descriptive_mark_only"


def test_liquidity_audit_detects_trade_exceeding_signal_session_participation():
    frame = market_fixture(65)
    result = replay(frame, CONFIG)
    assert result["trades"], "Adversarial test must exercise real modeled fills"
    original = audit(frame, CONFIG, analyze_pair(frame, CONFIG), result)
    assert next(item for item in original["checks"] if item["attack_id"] == "LIQUIDITY")["status"] == "pass"
    # Keep prices and filled trades fixed, but refute their signal-time liquidity.
    trade = result["trades"][0]
    frame.loc[frame.date == trade["signal_date"], "volume"] = 10
    changed = audit(frame, CONFIG, analyze_pair(frame, CONFIG), result)
    check = next(item for item in changed["checks"] if item["attack_id"] == "LIQUIDITY")
    assert check["status"] == "fail"


def test_missing_benchmark_fee_coverage_is_unavailable_without_fabricated_net_value():
    result = replay(market_fixture(45), {**CONFIG, 'min_volume': 1000000, 'cost_schedule': [
        {'schedule_id': 'late_only', 'effective_from': '2025-02-01', 'brokerage_per_lot': 29},
    ]})
    assert not result['trades']
    for benchmark in result['baselines'][1:]:
        assert benchmark['status'] == 'unavailable'
        assert benchmark['net_pnl'] is None
        assert 'fees unavailable' in benchmark['reason']


def test_missing_leg_sessions_are_not_filled_or_fabricated():
    frame = market_fixture(45)
    missing_date = sorted(frame.date.unique())[22]
    frame = frame.loc[~((frame.date == missing_date) & (frame.symbol == "GOLDTEN"))]
    result = analyze_pair(frame, {**CONFIG, "expiry_a": "2025-12-31", "expiry_b": "2025-12-31"})
    assert result["sessions"] == 44
    assert missing_date not in {item["date"] for item in result["series"]}
    assert not frame.duplicated(["symbol", "date", "expiry"]).any()


def test_historical_signal_prefix_unchanged_by_future_price_and_contract_mutations():
    frame = market_fixture(80)
    cutoff = sorted(frame.date.unique())[49]
    config = {**CONFIG, "start": frame.date.min(), "end": frame.date.max(), "cutoff": cutoff}
    original = replay(frame, config)
    assert any(event["type"] == "signal" for event in original["events"])
    changed = frame.copy(deep=True)
    changed.loc[changed.date > cutoff, ["open", "close", "volume", "open_interest"]] *= 50
    later_contract = frame.loc[frame.date > cutoff].copy()
    later_contract["expiry"] = "2026-12-31"
    changed = pd.concat([changed, later_contract], ignore_index=True)
    assert replay(changed, config) == original


def test_failed_hedge_scenario_prices_only_the_filled_leg_and_its_costs():
    frame = market_fixture(45)
    frame.loc[frame.symbol == 'GOLDM', 'close'] = 99500
    frame.loc[frame.symbol == 'GOLDTEN', 'close'] = 99900
    config = {**CONFIG, 'capital': 2000000, 'max_lots': 10, 'cost_bps': 5,
              'slippage_bps': 2, 'holding_days': 3, 'simulations': 50}
    result = ghost_market(frame, config)
    failed = next(item for item in result['scenarios'] if item['name'] == 'Failed hedge execution')
    assert failed['position']['lots_a'] == 1
    assert failed['position']['lots_b'] == 0
    assert failed['position']['residual_fine_g'] == pytest.approx(99.5)
    assert failed['exit_horizon'] - failed['entry_delay'] == 1
    # With flat empirical prices the disclosed volatility floor is 1e-6.
    # One long GOLDM lot is exposed to its adverse common-factor overlay;
    # the failed GOLDTEN leg contributes neither P&L nor fill fees.
    daily_move = -2e-6 / math.sqrt(3)
    entry = 99500 * (1 + daily_move)
    exit_price = 99500 * (1 + daily_move) ** 2
    gross = (exit_price - entry) * 10
    fees = (entry + exit_price) * 10 * (5 + 2 * 5) / 10000
    assert failed['median_net_pnl'] == pytest.approx(gross - fees, abs=1e-7)
    assert failed['worst_net_pnl'] == pytest.approx(gross - fees, abs=1e-7)
    assert 'No failure probability' in failed['execution_assumption']
    assert result == ghost_market(frame, config)
    assert result['historical_return_correlation'] is None


def test_capital_sensitivity_reexecutes_affordability_and_integer_position_limits():
    frame = market_fixture(65)
    config = {**CONFIG, 'capital': 2000000, 'max_lots': 10}
    result = survival_map(frame, config)
    slices = {item['parameter']: item for item in result['slices']}
    assert slices['capital']['value'] == 1000000
    assert slices['capital']['trades'] == 0  # cannot fund one lot of each leg
    assert slices['max_lots']['value'] == 5
    separately_replayed = replay(frame, {**config, 'max_lots': 5})
    assert slices['max_lots']['net_pnl'] == pytest.approx(separately_replayed['metrics']['net_pnl'])
    assert all(abs(trade['lots_a']) <= 5 and abs(trade['lots_b']) <= 5 for trade in separately_replayed['trades'])


def test_drawdown_series_reconciles_to_equity_peaks_and_reported_maximum():
    result = replay(market_fixture(65), CONFIG)
    assert result['equity'][0]['drawdown_fraction'] == 0
    running_peak = CONFIG['capital']
    for point in result['equity']:
        running_peak = max(running_peak, point['equity'])
        assert point['drawdown_fraction'] == pytest.approx((running_peak - point['equity']) / running_peak)
        assert point['drawdown_fraction'] >= 0
    assert max(point['drawdown_fraction'] for point in result['equity']) == result['metrics']['max_drawdown']


def test_bootstrap_never_allocates_a_block_beyond_its_output_horizon(monkeypatch):
    values = np.column_stack([np.arange(400) / 10000, np.arange(400) / 20000])
    original_arange = np.arange
    requested = []
    def tracked_arange(*args, **kwargs):
        requested.append(args[0])
        return original_arange(*args, **kwargs)
    monkeypatch.setattr(np, 'arange', tracked_arange)
    paths = paired_block_bootstrap(values, 50, 3, 400, 42)
    assert paths.shape == (50, 3, 2)
    assert max(requested) <= 3
    assert np.array_equal(paths, paired_block_bootstrap(values, 50, 3, 3, 42))


@pytest.mark.parametrize('mode,label', [('real', 'IMPORTED UNVERIFIED DATA'), ('synthetic', 'SYNTHETIC TEST DATA')])
def test_imported_sources_keep_explicit_unverified_or_synthetic_provenance(tmp_path, mode, label):
    # Even a plausible exchange-shaped upload is not independently authenticated.
    frame = market_fixture(3)
    storage = Storage(tmp_path / mode)
    report = storage.import_bytes('hypothetical-audit-fixture.csv', frame.to_csv(index=False).encode(), mode=mode)
    assert report['rows_imported'] == 6
    assert report['provenance'] == label
    assert not report['source_authenticity_verified']
    assert report['source_identifier'] == 'sha256:' + report['source_hash']
    assert report['source_url'] is None
    assert report['timestamp']
    assert report['imported_coverage']['start'] == frame.date.min()
    assert report['imported_coverage']['end'] == frame.date.max()
    assert len(report['imported_coverage']['contracts']) == 2
    assert all(contract['sessions'] == 3 for contract in report['imported_coverage']['contracts'])
    assert storage.imports(mode)[0]['provenance'] == label
    summary = storage.summary(mode)
    assert summary['provenance'] == label
    assert not summary['has_real_history']
    assert summary['has_imported_history'] == (mode == 'real')
    assert all(item['provenance'] == label and item['source_hashes'] == [report['source_hash']]
               for item in storage.contracts(mode))
