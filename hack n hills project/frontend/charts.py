"""Chart measurement labels; no statistics or economic calculations."""


UNITS = {
    "INR per fine gram": {"normalized_a", "normalized_b", "normalized_spread", "residual", "fine_price", "normalized_price", "reference", "median", "std", "mad", "maturity_component", "factor_price"},
    "Historical standard deviations": {"zscore", "z_score", "robust_zscore"},
    "INR · hypothetical": {"net_pnl", "gross_pnl", "equity", "costs", "realized_gross", "unrealized_gross", "costs_paid", "median_net_pnl", "p05_net_pnl", "p95_net_pnl"},
    "Drawdown depth · fraction of peak": {"drawdown_fraction"},
    "Calendar days": {"days_to_expiry_a", "days_to_expiry_b", "days_to_expiry"},
    "Lots": {"volume_a", "volume_b", "oi_a", "oi_b", "lots_a", "lots_b"},
}


def measure_groups(columns):
    grouped = {unit: [name for name in columns if name in fields] for unit, fields in UNITS.items()}
    grouped = {unit: names for unit, names in grouped.items() if names}
    known = {name for names in grouped.values() for name in names}
    for name in columns:
        if name not in known:
            # Distinct raw quote bases and unrelated ratios must not share axes.
            grouped[f"{name.replace('_', ' ').title()} · backend units"] = [name]
    return grouped
