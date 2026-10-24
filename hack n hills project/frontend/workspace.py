"""Browser-session state for research inputs and dataset freshness."""
from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

import streamlit as st


PREFERENCE_FIELDS = ("cost_bps", "slippage_bps", "seed", "simulations", "volatility_stress", "cost_schedule")
INPUT_FIELDS = ("window", "z_threshold", "baseline", "capital", "max_lots", "min_volume",
                "min_oi", "holding_days", "execution_delay", "exit_delay")
AUTOMATIC_EXPIRY = "Automatic · one exact contract"


def clear_results() -> None:
    """Live results are scoped to the connected dataset; certificates stay on disk."""
    for key in list(st.session_state):
        if key.startswith("result_") or key in ("pair_scan", "replay_state", "guided_result"):
            del st.session_state[key]


def apply_pending_preset() -> None:
    pending = st.session_state.pop("pending_research_preset", None)
    if not pending:
        return
    config = pending["config"]
    mode = config.get("mode", "real")
    st.session_state["mode_label"] = "Synthetic demonstration" if mode == "synthetic" else "Real MCX history"
    pair = config.get("pair", ["GOLDM", "GOLDTEN"])
    st.session_state["pair_a"], st.session_state["pair_b"] = pair
    for leg, symbol in zip(("a", "b"), pair):
        st.session_state[f"expiry_{leg}_{mode}_{symbol}"] = config.get(f"expiry_{leg}") or AUTOMATIC_EXPIRY
    for name in ("start", "end", "cutoff"):
        key = f"{name}_{mode}"
        st.session_state.pop(key, None)
        if config.get(name):
            st.session_state[key] = date.fromisoformat(config[name])
    for name in INPUT_FIELDS:
        if name in config:
            st.session_state[name] = config[name]
    preferences = st.session_state.setdefault("preferences", {})
    for name in PREFERENCE_FIELDS:
        if name in config:
            preferences[name] = config[name]
        st.session_state.pop("setting_" + name, None)
    for name in ("fee_schedule_json", "survival_cost", "survival_slippage"):
        st.session_state.pop(name, None)
    st.session_state["preset_notice"] = f"Loaded preset: {pending['name']}"
    st.session_state.setdefault("research_configs", {})[mode] = dict(config)
    for key in list(st.session_state):
        if key.startswith("guide_input_"):
            del st.session_state[key]


def remember_config(config: dict) -> None:
    st.session_state.setdefault("research_configs", {})[config["mode"]] = dict(config)


def default_config(summary: Any, mode: str) -> dict:
    summary = summary or {}
    first = summary.get("start") or summary.get("date_min") or (date.today() - timedelta(days=365)).isoformat()
    last = summary.get("end") or summary.get("date_max") or date.today().isoformat()
    config = {"pair": ["GOLDM", "GOLDTEN"], "mode": mode, "start": first, "end": last, "cutoff": last,
              "window": 20, "z_threshold": 2.0, "baseline": "C", "capital": 1e7, "max_lots": 100,
              "min_volume": 10, "min_oi": 10, "holding_days": 5, "execution_delay": 1, "exit_delay": 0,
              "cost_bps": 5.0, "slippage_bps": 2.0, "seed": 42, "simulations": 500,
              "volatility_stress": 1.0, "cost_schedule": []}
    config.update(st.session_state.get("research_configs", {}).get(mode, {}))
    config.update({k: v for k, v in st.session_state.get("preferences", {}).items() if k in PREFERENCE_FIELDS})
    for name, fallback in (("start", first), ("end", last), ("cutoff", last)):
        config[name] = config.get(name) or fallback
    return config


def restore_research_inputs(config: dict) -> None:
    """Restore controls hidden during Guided Mode without overwriting user edits."""
    mode = config["mode"]
    for key, value in zip(("pair_a", "pair_b"), config["pair"]):
        st.session_state.setdefault(key, value)
    for name in INPUT_FIELDS:
        st.session_state.setdefault(name, config[name])
    for name in ("start", "end", "cutoff"):
        st.session_state.setdefault(f"{name}_{mode}", date.fromisoformat(config[name]))
    for leg, symbol in zip(("a", "b"), config["pair"]):
        st.session_state.setdefault(f"expiry_{leg}_{mode}_{symbol}", config.get(f"expiry_{leg}") or AUTOMATIC_EXPIRY)


def observe_dataset(mode: str, summary: Any, contracts: Any) -> None:
    if summary is None or contracts is None:
        return
    signatures = st.session_state.setdefault("dataset_signatures", {})
    signature = json.dumps([summary, contracts], sort_keys=True, default=str)
    previous = signatures.get(mode)
    if previous is not None and previous != signature:
        clear_results()
        st.session_state["dataset_notice"] = "The dataset changed. Run your calculations again using the refreshed observations."
    signatures[mode] = signature


def sync_connection(base: str) -> None:
    previous = st.session_state.get("connected_api")
    if previous is not None and previous != base:
        clear_results()
        st.session_state.pop("metadata_cache", None)
        st.session_state.pop("dataset_signatures", None)
        st.session_state.pop("last_import_result", None)
        st.session_state.pop("last_demo_result", None)
        st.session_state.pop("guided_job", None)
        st.session_state.pop("research_configs", None)
        for mode in ("real", "synthetic"):
            for name in ("start", "end", "cutoff"):
                st.session_state.pop(f"{name}_{mode}", None)
        st.session_state["dataset_notice"] = "API connection changed. Coverage and results have been reset."
    st.session_state["connected_api"] = base
