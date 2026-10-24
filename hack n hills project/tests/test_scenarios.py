import numpy as np

from backend.services.scenarios import paired_block_bootstrap, ghost_market, survival_map
from tests.test_financial import CONFIG, market_fixture


def test_bootstrap_preserves_paired_dependence_exactly():
    a = np.linspace(-0.02, 0.02, 40)
    pairs = np.column_stack([a, 2 * a])
    paths = paired_block_bootstrap(pairs, 100, 10, 4, 42)
    assert np.allclose(paths[:, :, 1], 2 * paths[:, :, 0])
    assert np.array_equal(paths, paired_block_bootstrap(pairs, 100, 10, 4, 42))


def test_ghost_seed_and_all_stress_classes():
    data = market_fixture(70)
    first = ghost_market(data, CONFIG)
    assert first == ghost_market(data, CONFIG)
    assert len(first["scenarios"]) == 11
    base = first["scenarios"][0]
    cost = first["scenarios"][1]
    assert cost["median_net_pnl"] < base["median_net_pnl"]
    sensitivity = first["cost_sensitivity"]
    assert sensitivity[0]["median_net_pnl"] > sensitivity[-1]["median_net_pnl"]
    assert first["scenarios"] != ghost_market(data, {**CONFIG, "seed": 43})["scenarios"]


def test_survival_grid_reexecutes_cost_and_delay():
    result = survival_map(market_fixture(65), CONFIG)
    assert len(result["cells"]) == 9
    assert any(c["trades"] > 0 for c in result["cells"])
    for delay in result["axes"]["execution_delay"]:
        column = [c for c in result["cells"] if c["execution_delay"] == delay]
        assert column[0]["net_pnl"] >= column[-1]["net_pnl"]
    assert len(result["slices"]) == 4
