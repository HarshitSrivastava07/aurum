"""Local Streamlit client; no financial calculations or contract rules live here.

Run: streamlit run frontend/app.py
The HTTP API is the sole source of research results and contract metadata.
"""
from __future__ import annotations

import html
import json
import os
import time
from datetime import date, timedelta
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

from frontend.presets import render_presets
from frontend.workspace import (AUTOMATIC_EXPIRY, apply_pending_preset, clear_results,
                                observe_dataset, sync_connection, default_config,
                                remember_config, restore_research_inputs)
from frontend.guided import welcome, wizard, learning
from frontend.explanations import TERMS, provenance
from frontend.charts import measure_groups
from frontend.theme import CSS, PALETTE, HEATMAP, style_chart


PAGES = [
    "Command Center", "Relative Value Explorer", "Futures Curve Laboratory",
    "Mirage Investigation", "Ghost Market", "Market Red Team",
    "Time-Locked Replay", "Profit Survival Map", "Anomaly DNA",
    "Contract Genome", "Evidence Center", "Data Management", "Settings",
]
GUIDED_PAGES = ["Welcome", "Guided Investigation", "Learn gold futures", "Evidence Center", "Data Management", "Settings"]
PRODUCTS = ["GOLDM", "GOLDTEN", "GOLDGUINEA", "GOLDPETAL"]
GOLD = PALETTE[0]
SYNTHETIC_LABEL = "SYNTHETIC DEMONSTRATION — NOT ACTUAL MCX PERFORMANCE"
DESCRIPTIONS = {
    "Guided Investigation": "Choose a question, compare actual observed contracts and follow the evidence step by step.",
    "Learn gold futures": "Learn the essential terms and explore a clearly hypothetical purity comparison.",
    "Welcome": "A guided laboratory for investigating gold futures price differences.",
    "Command Center": "A clear view of the evidence. Every conclusion begins with the data you actually have.",
    "Relative Value Explorer": "Compare quotation, purity and maturity effects across exact gold futures contracts.",
    "Futures Curve Laboratory": "Inspect listed maturities, empirical carry and the limits of curve-based explanations.",
    "Mirage Investigation": "Discover a candidate, challenge its explanation and preserve the entire investigation.",
    "Ghost Market": "Explore how a research conclusion behaves under reproducible, adverse scenarios.",
    "Market Red Team": "Executable checks challenge the assumptions behind each candidate conclusion.",
    "Time-Locked Replay": "Reveal one historical session at a time. The information cutoff follows the replay clock.",
    "Profit Survival Map": "Find the assumptions under which hypothetical results survive modeled costs and stress.",
    "Anomaly DNA": "Find interpretable historical analogs using only evidence available before the selected cutoff.",
    "Contract Genome": "Inspect the specification registry and the exact contracts present in your dataset.",
    "Evidence Center": "Revisit accepted, rejected and unresolved research. Export and reproduce preserved investigations.",
    "Data Management": "Import exchange exports, inspect validation and follow every observation back to its source.",
    "Settings": "Set explicit research assumptions. These settings are sent to the backend on the next calculation.",
}


class APIError(RuntimeError):
    """An actionable, safe error presented to the local application user."""


def api_base() -> str:
    return st.session_state.get("preferences", {}).get("api_url", os.getenv("AURUM_API_URL", "http://127.0.0.1:8000")).strip().rstrip("/")


def api(method: str, path: str, *, params: dict | None = None,
        body: dict | None = None, files: Any = None, data: dict | None = None) -> Any:
    preferences = st.session_state.get("preferences", {})
    base = api_base()
    timeout = int(preferences.get("request_timeout", 120))
    try:
        response = requests.request(method, base + path, params=params, json=body,
                                    files=files, data=data, timeout=(5, timeout))
    except requests.exceptions.Timeout as exc:
        raise APIError("The backend did not finish within the configured timeout. Reduce the simulation size or increase the timeout in Settings.") from exc
    except requests.exceptions.ConnectionError as exc:
        raise APIError("The research API is unavailable. Start the FastAPI service and check the API address in Settings.") from exc
    except requests.exceptions.RequestException as exc:
        raise APIError("The API request could not be completed. Check the connection and retry.") from exc
    try:
        payload = response.json()
    except ValueError as exc:
        raise APIError(f"The API returned an unreadable response (HTTP {response.status_code}).") from exc
    if not response.ok:
        detail = payload.get("detail", "Request rejected") if isinstance(payload, dict) else "Request rejected"
        if isinstance(detail, list):
            detail = "; ".join(str(item.get("msg", item)) if isinstance(item, dict) else str(item) for item in detail)
        raise APIError(f"HTTP {response.status_code}: {str(detail)[:900]}")
    return payload


def safe_get(path: str, params: dict | None = None, quiet: bool = False) -> Any:
    try:
        return api("GET", path, params=params)
    except APIError as exc:
        if not quiet:
            st.error(str(exc))
        return None


def dataset_metadata(mode: str) -> tuple[Any, Any]:
    """Reuse metadata during control changes; refresh on demand or after 30 seconds."""
    cache = st.session_state.setdefault("metadata_cache", {})
    key = (api_base(), mode)
    saved = cache.get(key)
    if saved and time.monotonic() - saved[0] < 30:
        return saved[1], saved[2]
    summary = safe_get("/api/summary", {"mode": mode}, quiet=True)
    contracts = safe_get("/api/contracts", {"mode": mode}, quiet=True) if summary is not None else None
    if summary is not None and contracts is not None:
        cache[key] = (time.monotonic(), summary, contracts)
    return summary, contracts


def navigate(page: str, mode: str | None = None) -> None:
    st.session_state["page"] = page
    if page not in GUIDED_PAGES:
        st.session_state["experience"] = "Research Mode"
    elif page in ("Welcome", "Guided Investigation", "Learn gold futures"):
        st.session_state["experience"] = "Guided Mode"
    if mode:
        st.session_state["mode_label"] = "Synthetic demonstration" if mode == "synthetic" else "Real MCX history"


def change_experience() -> None:
    st.session_state["page"] = "Welcome" if st.session_state["experience"] == "Guided Mode" else "Command Center"


def records(payload: Any, *keys: str) -> list[dict]:
    """Extract API records without computing or changing financial values."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in (*keys, "records", "rows", "data", "items"):
            if isinstance(payload.get(key), list):
                return [item for item in payload[key] if isinstance(item, dict)]
    return []


def field(payload: Any, *keys: str, default: Any = None) -> Any:
    if isinstance(payload, dict):
        for key in keys:
            if payload.get(key) is not None:
                return payload[key]
    return default


def as_date(value: Any, default: date) -> date:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return default


def caption_title(label: str) -> None:
    st.markdown(f'<div class="section-label">{html.escape(label)}</div>', unsafe_allow_html=True)


def show_table(rows: list[dict], *, key: str, download: bool = False) -> None:
    if not rows:
        st.info("No records are available for these filters.")
        return
    frame = pd.DataFrame(rows)
    # JSON preserves nested audit evidence in a readable table cell.
    for col in frame.columns:
        if frame[col].map(lambda value: isinstance(value, (dict, list))).any():
            frame[col] = frame[col].map(lambda value: json.dumps(value, default=str) if isinstance(value, (dict, list)) else value)
    st.dataframe(frame, width="stretch", hide_index=True)
    if download:
        export_frame = frame.copy()
        mode = "synthetic" if st.session_state.get("mode_label") == "Synthetic demonstration" else "real"
        export_frame["data_provenance"] = export_frame["mode"].map(provenance) if "mode" in export_frame else provenance(mode)
        st.download_button("Export displayed records · CSV", export_frame.to_csv(index=False),
                           file_name=f"aurum-x-{key}.csv", mime="text/csv", key=f"csv_{key}")


def show_notices(result: Any) -> None:
    if not isinstance(result, dict):
        return
    for name in ("message", "conclusion", "reason", "status"):
        value = result.get(name)
        if isinstance(value, str) and value:
            st.info(value.replace("_", " ") if name == "status" else value)
    for name in ("warnings", "limitations", "unverified_assumptions"):
        value = result.get(name)
        if value:
            items = value if isinstance(value, list) else [value]
            for item in items[:12]:
                st.warning(str(item))


def show_result(result: Any, key: str, *, chart_kind: str = "line") -> None:
    """Presentation of typed backend results plus a complete inspectable record."""
    if result is None:
        return
    show_notices(result)
    if isinstance(result, dict):
        verdict = result.get("verdict") or result.get("final_verdict")
        if verdict:
            st.markdown(f"### {str(verdict)}")
        metric_keys = ("observations", "sessions", "aligned_sessions", "sample_size", "candidate_count", "trades", "net_pnl", "gross_pnl",
                       "median_pnl", "positive_fraction", "max_drawdown", "total_costs", "costs", "execution_feasibility")
        metric_source = result.get("metrics") if isinstance(result.get("metrics"), dict) else result
        scalar_metrics = [(name, metric_source[name]) for name in metric_keys if name in metric_source and isinstance(metric_source[name], (str, int, float))]
        for offset in range(0, len(scalar_metrics), 4):
            group = scalar_metrics[offset:offset + 4]
            columns = st.columns(len(group))
            for column, (name, value) in zip(columns, group):
                column.metric(name.replace("_", " ").title(), f"{value:,.3f}" if isinstance(value, float) else str(value))
    result_rows = records(result, "series", "equity", "history", "timeline", "points", "curve", "curves", "grid", "cells", "scenarios", "attacks", "checks", "analogs", "trades", "candidates", "results")
    if result_rows:
        frame = pd.DataFrame(result_rows)
        chart_mode = field(result, "mode", default="synthetic" if st.session_state.get("mode_label") == "Synthetic demonstration" else "real")
        st.caption(f"Chart and table source: {provenance(chart_mode)}. Values come from the backend calculation; inspect its assumptions below.")
        numeric = [col for col in frame.select_dtypes(include="number").columns if col not in ("id", "seed")]
        temporal = next((col for col in ("date", "Date", "session", "trade_date", "expiry", "expiry_date", "days_to_expiry", "dte", "cutoff") if col in frame.columns), None)
        sensitivity_axis = next((name for name in ("execution_delay", "slippage_bps") if name in frame.columns), None)
        if chart_kind == "heatmap" and "cost_bps" in frame.columns and sensitivity_axis:
            outcome = next((col for col in ("net_pnl", "median_pnl", "net_edge", "net") if col in frame.columns), None)
            if outcome and not frame.duplicated(["cost_bps", sensitivity_axis]).any():
                pivot = frame.pivot(index=sensitivity_axis, columns="cost_bps", values=outcome)
                fig = go.Figure(go.Heatmap(x=pivot.columns, y=pivot.index, z=pivot.values,
                                          colorscale=HEATMAP, zmid=0,
                                          colorbar=dict(title="Hypothetical ₹")))
                fig.update_xaxes(title="Assumed transaction cost · bps")
                fig.update_yaxes(title="Entry delay · sessions" if sensitivity_axis == "execution_delay" else "Assumed slippage · bps")
                st.plotly_chart(style_chart(fig, "Modeled net P&L sensitivity"), width="stretch", key=f"plot_{key}")
        elif temporal and numeric:
            preferred = [col for col in ("normalized_a", "normalized_b", "residual", "z_score", "zscore", "normalized_price", "fine_price", "close", "Close", "net_pnl", "equity") if col in numeric]
            groups = measure_groups(numeric)
            default_measure = (preferred or numeric)[0]
            default_group = next(unit for unit, names in groups.items() if default_measure in names)
            unit = st.selectbox("Chart units", list(groups), index=list(groups).index(default_group), key=f"units_{key}")
            choices = [name for name in preferred if name in groups[unit]] or groups[unit][:2]
            chosen = st.multiselect("Chart measures", groups[unit], default=choices[:2], key=f"measures_{key}_{unit}")
            if chosen:
                fig = px.line(frame, x=temporal, y=chosen, color_discrete_sequence=PALETTE)
                fig.update_yaxes(title=unit)
                fig.update_xaxes(title=temporal.replace("_", " ").title())
                st.plotly_chart(style_chart(fig, f"{', '.join(name.replace('_', ' ') for name in chosen)} · {frame[temporal].min()} to {frame[temporal].max()}"), width="stretch", key=f"plot_{key}")
        elif chart_kind == "histogram" and "modeled_outcomes" in frame.columns:
            chosen_name = st.selectbox("Stress scenario distribution", frame["name"].tolist(), key=f"scenario_{key}")
            sample = next(row["modeled_outcomes"] for row in result_rows if row["name"] == chosen_name)
            if sample:
                fig = px.histogram(x=sample, nbins=30, labels={"x": "Hypothetical net P&L · ₹"}, color_discrete_sequence=[GOLD])
                st.plotly_chart(style_chart(fig, chosen_name), width="stretch", key=f"plot_{key}")
                st.caption(f"Displayed sample: {len(sample)} simulated outcomes. Scenario summary statistics are computed by the backend from all {result.get('simulations', 'configured')} paths.")
        elif chart_kind == "histogram" and numeric:
            outcome = next((col for col in ("net_pnl", "pnl", "outcome") if col in numeric), numeric[0])
            fig = px.histogram(frame, x=outcome, nbins=40, color_discrete_sequence=[GOLD])
            st.plotly_chart(style_chart(fig, "Hypothetical scenario outcomes"), width="stretch", key=f"plot_{key}")
        caption_title("Calculated records")
        show_table(result_rows, key=key, download=True)
    if isinstance(result, dict):
        # Some engines return raw bootstrap observations as numeric arrays.
        distribution = next((result[name] for name in ("net_pnl_distribution", "distribution", "pnl_distribution") if isinstance(result.get(name), list) and all(isinstance(v, (int, float)) for v in result[name])), None)
        if distribution:
            fig = px.histogram(x=distribution, nbins=40, labels={"x": "Hypothetical net P&L · ₹"}, color_discrete_sequence=[GOLD])
            st.plotly_chart(style_chart(fig, "Simulated outcomes · not a calibrated probability forecast"), width="stretch", key=f"distribution_{key}")
        secondary_records = {
            "calendar_spreads": "Calendar spreads · normalized monetary basis",
            "decomposition": "Unchanged contract, roll-down and residual curve movement",
            "events": "Chronological decision and execution events",
            "walk_forward": "Historical training windows",
            "baselines": "Reference baselines · hypothetical",
            "ledger": "Hypothesis and experiment history",
            "cost_sensitivity": "Assumed transaction cost sensitivity",
            "slices": "Holding, slippage, liquidity and exit sensitivity",
            "boundaries": "Highest tested profitable cost boundaries",
            "volatility_and_liquidity_stresses": "Counterfactual volatility and liquidity stresses",
        }
        if "equity" in result:
            secondary_records["trades"] = "Completed hypothetical trades · exact contracts"
        for name, title in secondary_records.items():
            section = result.get(name)
            if isinstance(section, list) and section:
                with st.expander(title):
                    show_table(records(section), key=f"{key}_{name}", download=True)
        nested_names = {
            "mirage": "Mirage", "analytics": "Relative value", "ghost": "Ghost Market",
            "ghost_market": "Ghost Market", "audit": "Red Team", "red_team": "Red Team",
            "replay": "Historical replay", "analogs": "Anomaly DNA", "survival": "Survival",
            "attribution": "Attribution", "holdout": "Held-out evaluation",
            "baseline_comparison": "Baseline comparison",
        }
        engine_results = result.get("outputs", result)
        nested = [(name, title) for name, title in nested_names.items() if isinstance(engine_results.get(name), dict)]
        if nested:
            tabs = st.tabs([title for _, title in nested])
            for tab, (name, _) in zip(tabs, nested):
                with tab:
                    show_result(engine_results[name], f"{key}_{name}", chart_kind="histogram" if "ghost" in name else "heatmap" if name == "survival" else "line")
    with st.expander("Full backend evidence and assumptions", expanded=not bool(result_rows)):
        st.json(result, expanded=2)


def result_key(page: str, config: dict) -> str:
    return page + ":" + json.dumps(config, sort_keys=True)


def run_engine(page: str, endpoint: str, config: dict, button: str, chart_kind: str = "line") -> None:
    if st.button(button, type="primary", key=f"run_{page}", width="stretch"):
        try:
            with st.spinner("Calculating from the selected dataset and assumptions…"):
                result = api("POST", endpoint, body=config)
            st.session_state["result_" + page] = (result_key(page, config), result)
        except APIError as exc:
            st.session_state.pop("result_" + page, None)
            st.error(str(exc))
    saved = st.session_state.get("result_" + page)
    if saved and saved[0] == result_key(page, config):
        st.download_button("Download result · JSON", json.dumps({"provenance": provenance(config["mode"]), "config": config, "result": saved[1]}, indent=2, ensure_ascii=False, default=str),
                           file_name=f"aurum-x-{page.lower().replace(' ', '-')}.json", mime="application/json", key=f"download_{page}")
        show_result(saved[1], page.replace(" ", "_"), chart_kind=chart_kind)
    elif saved:
        st.info("The assumptions have changed. Run the calculation again to produce a matching result.")
    else:
        st.caption("Results appear after a backend calculation. Insufficient evidence is a valid research outcome.")


def research_controls(summary: Any, contracts: Any, mode: str) -> dict:
    """Only collect inputs; eligibility and financial interpretation belong to API."""
    with st.sidebar.expander("Research scope", expanded=True):
        caption_title("Research scope")
        pair_a = st.selectbox("First contract", PRODUCTS, index=0, key="pair_a")
        pair_b = st.selectbox("Second contract", [p for p in PRODUCTS if p != pair_a], key="pair_b")
        contract_rows = records(contracts, "contracts")
        def expiries(symbol: str) -> list[str]:
            return sorted({str(row.get("expiry") or row.get("expiry_date") or row.get("ExpiryDate"))[:10]
                           for row in contract_rows if str(row.get("symbol") or row.get("Symbol")) == symbol
                           and (row.get("expiry") or row.get("expiry_date") or row.get("ExpiryDate"))})
        def expiry_options(leg: str, symbol: str) -> list[str]:
            available = expiries(symbol)
            selected = st.session_state.get(f"expiry_{leg}_{mode}_{symbol}")
            if selected and selected != AUTOMATIC_EXPIRY and selected not in available:
                available.append(selected)
                st.caption(f"Preset expiry {selected} is not present in this dataset.")
            return [AUTOMATIC_EXPIRY, *sorted(available)]
        expiry_a = st.selectbox("First expiry", expiry_options("a", pair_a), key=f"expiry_a_{mode}_{pair_a}",
                                help="The backend selects one exact expiry when automatic; it does not stitch a near-month price history.")
        expiry_b = st.selectbox("Second expiry", expiry_options("b", pair_b), key=f"expiry_b_{mode}_{pair_b}")
        today = date.today()
        minimum = as_date(field(summary, "date_min", "min_date", "start_date", "first_date", "start"), today - timedelta(days=365))
        maximum = as_date(field(summary, "date_max", "max_date", "end_date", "last_date", "end"), today)
        earliest = date.min
        start = st.date_input("From", value=minimum, min_value=earliest, max_value=today, key=f"start_{mode}")
        end = st.date_input("Through", value=maximum, min_value=earliest, max_value=today, key=f"end_{mode}")
        cutoff = st.date_input("Information cutoff", value=maximum, min_value=earliest, max_value=today, key=f"cutoff_{mode}",
                               help="The backend excludes observations after this date.")
        window = st.number_input("Historical window · sessions", 5, 252, value=20, step=1, key="window")
        baseline = st.selectbox("Decision policy", ["C", "B", "A"],format_func=lambda v:{'A':'A · Normalized spread','B':'B · Maturity aware','C':'C · Full investigation'}[v],key="baseline")
        threshold = st.number_input("Anomaly threshold · Z", 0.5, 10.0, value=2.0, step=0.1, key="z_threshold", help=TERMS["Z-score"])
        with st.expander("Execution assumptions"):
            st.number_input("Capital limit · ₹", min_value=0.0, max_value=1e12, value=10_000_000.0, step=100000.0, key="capital")
            st.number_input("Maximum lots per leg", 1, 1000, value=100, key="max_lots")
            st.number_input("Minimum session volume · lots", 1, 100000000, value=10, key="min_volume")
            st.number_input("Minimum open interest · lots", 1, 100000000, value=10, key="min_oi")
            st.number_input("Holding period · sessions", 1, 60, value=5, key="holding_days")
            st.number_input("Entry delay · sessions", 1, 20, value=1, key="execution_delay", help="A signal cannot fill at that same session's close.")
            st.number_input("Additional exit delay · sessions", 0, 20, value=0, key="exit_delay")
    config = {
        "pair": [pair_a, pair_b], "mode": mode, "start": start.isoformat(), "end": end.isoformat(),
        "cutoff": cutoff.isoformat(), "window": int(window), "z_threshold": float(threshold), "baseline":baseline,
    }
    for key, default in {"capital": 1e7, "max_lots": 100, "min_volume": 10, "min_oi": 10,
                         "holding_days": 5, "execution_delay": 1, "exit_delay": 0, "cost_bps": 5.0,
                         "slippage_bps": 2.0, "seed": 42, "simulations": 500, "volatility_stress": 1.0}.items():
        config[key] = st.session_state.get("preferences", {}).get(key, st.session_state.get(key, default))
    if not expiry_a.startswith("Automatic"):
        config["expiry_a"] = expiry_a
    if not expiry_b.startswith("Automatic"):
        config["expiry_b"] = expiry_b
    config['cost_schedule']=st.session_state.get('preferences',{}).get('cost_schedule',[])
    return config


def getting_started(summary: Any, config: dict) -> None:
    rows = field(summary, "row_count", "rows", "observations", "record_count", default=0)
    if summary is None:
        with st.container(border=True):
            st.subheader("Connect your research workspace")
            st.write("Start the research API, then refresh the connection to load your data.")
            st.code("powershell -ExecutionPolicy Bypass -File scripts\\start.ps1", language="powershell")
            st.button("Open connection settings", on_click=navigate, args=("Settings",), key="connect_settings")
        return
    if rows:
        return
    with st.container(border=True):
        st.subheader("Start your first investigation")
        st.write("Choose a dataset, compare two contracts, then preserve the evidence. This environment has no daily observations yet.")
        left, right = st.columns(2)
        with left:
            st.markdown("**Explore the demonstration**")
            st.caption("Use reproducible synthetic prices to learn the complete workflow.")
            if config["mode"] == "real":
                st.button("Explore synthetic demo", type="primary", on_click=navigate, args=("Command Center", "synthetic"), key="explore_demo", width="stretch")
            elif st.button("Create demo dataset", type="primary", key="create_demo", width="stretch"):
                try:
                    with st.spinner("Preparing your demonstration dataset…"):
                        api("POST", "/api/demo", body={"seed": int(config["seed"])})
                    st.session_state["refresh_scope"] = "synthetic"
                    st.rerun()
                except APIError as exc:
                    st.error(str(exc))
        with right:
            st.markdown("**Bring your own daily history**")
            st.caption("Import daily contract exports and inspect source validation.")
            st.button("Import market data", on_click=navigate, args=("Data Management", "real"), key="start_import", width="stretch")


def command_center(summary: Any, contracts: Any, config: dict) -> None:
    getting_started(summary, config)
    caption_title("Evidence before conviction")
    columns = st.columns(4)
    columns[0].metric("Imported observations", field(summary, "row_count", "rows", "observations", "record_count", default="—"))
    columns[1].metric("Exact contracts", field(summary, "contracts_count", "contract_count", "contracts", default="—") if not isinstance(field(summary, "contracts"), list) else len(summary["contracts"]))
    columns[2].metric("First observed session", field(summary, "date_min", "min_date", "start_date", "first_date", "start", default="—"))
    columns[3].metric("Last observed session", field(summary, "date_max", "max_date", "end_date", "last_date", "end", default="—"))
    caption_title("Choose your next step")
    quick_actions = [
        ("⚖️ Compare contracts", "Inspect normalized spreads and exact expiries across products.", "Relative Value Explorer"),
        ("🛡️ Challenge an idea", "Test your assumptions against adverse scenarios and costs.", "Ghost Market"),
        ("📋 Review evidence", "Open, export and reproduce saved investigations.", "Evidence Center"),
    ]
    for column, (title, description, destination) in zip(st.columns(3), quick_actions):
        with column, st.container(border=True):
            st.markdown(f"**{title}**")
            st.caption(description)
            st.button("Open workspace", key=f"quick_{destination}", on_click=navigate, args=(destination,), width="stretch")
    left, right = st.columns([1.4, 1])
    with left:
        st.markdown("### The research pipeline")
        st.markdown("**01 · Normalize**  →  **02 · Investigate**  →  **03 · Challenge**  →  **04 · Preserve**")
        st.write("An unusual spread is a research question. Units, purity, maturity, location, trading costs and contract lifecycle all affect its interpretation.")
        st.caption("Results distinguish statistical evidence from execution feasibility. Session prices do not establish that both legs could have filled.")
    with right:
        st.markdown("### Selected scope")
        st.write(f"**{config['pair'][0]} / {config['pair'][1]}**")
        st.write(f"{config['start']} → {config['end']} · cutoff {config['cutoff']}")
        st.caption(f"Assumed costs {config['cost_bps']:g} bps · slippage {config['slippage_bps']:g} bps · seed {config['seed']}")
    st.divider()
    run_engine("Command Center", "/api/investigations", config, "▶ Run full investigation")
    caption_title("Available expiry-specific contracts")
    show_table(records(contracts, "contracts"), key="overview_contracts")
    with st.expander("Dataset coverage and quality"):
        st.json(summary or {"status": "API coverage unavailable"})



def replay_page(config: dict) -> None:
    st.caption("Each step makes a new API request with that session as the strict information cutoff. No future observations are supplied to the displayed result.")
    scope = result_key("replay_scope", config)
    if st.button("Load available replay sessions", type="primary"):
        try:
            payload = api("GET", "/api/sessions", params={"mode": config["mode"], "start": config["start"], "end": min(config["end"], config["cutoff"]), "symbol": config["pair"][0]})
            dates = payload["sessions"]
            st.session_state["replay_state"] = {"scope": scope, "sessions": dates, "index": -1, "result": None}
            if not dates:
                st.info("No trading sessions are available in this scope.")
        except APIError as exc:
            st.error(str(exc))
    state = st.session_state.get("replay_state")
    if not state:
        return
    if state["scope"] != scope:
        st.info("Research assumptions changed. Load sessions again to start a matching replay.")
        return
    sessions = state["sessions"]
    if not sessions:
        return
    current = state["index"]
    left, middle, right = st.columns([1, 1, 2])
    reset = left.button("Reset clock", disabled=current < 0)
    advance = middle.button("Next session →", type="primary", disabled=current >= len(sessions) - 1)
    right.metric("Revealed through", sessions[current] if current >= 0 else "No sessions revealed")
    if reset:
        state.update(index=-1, result=None)
        st.rerun()
    if advance:
        next_index = current + 1
        step_config = dict(config, end=sessions[next_index], cutoff=sessions[next_index])
        try:
            with st.spinner(f"Reconstructing available evidence on {sessions[next_index]}…"):
                result = api("POST", "/api/replay", body=step_config)
            state.update(index=next_index, result=result)
            st.rerun()
        except APIError as exc:
            st.error(str(exc))
    st.progress((state["index"] + 1) / len(sessions), text=f"{state['index'] + 1} of {len(sessions)} observed sessions revealed")
    show_result(state["result"], "replay")


def evidence_page(mode: str) -> None:
    listing = safe_get("/api/investigations")
    items = records(listing, "investigations")
    items = [item for item in items if field(item, "mode") == mode]
    show_table(items, key="investigation_history")
    identifiers = [str(field(item, "id", "investigation_id")) for item in items if field(item, "id", "investigation_id")]
    if not identifiers:
        st.caption("Run an investigation to create the first evidence certificate in this data mode.")
        return
    selected = st.selectbox("Investigation to inspect", identifiers)
    certificate = safe_get(f"/api/investigations/{selected}")
    if certificate is None:
        return
    show_result(certificate, "certificate")
    st.download_button("Export Evidence Certificate · JSON", json.dumps(certificate, indent=2, ensure_ascii=False, default=str),
                       file_name=f"aurum-x-{selected}.json", mime="application/json", type="primary")
    if st.button("Reproduce preserved investigation"):
        try:
            with st.spinner("Recalculating the preserved snapshot and configuration…"):
                result = api("POST", f"/api/investigations/{selected}/reproduce")
            show_result(result, "reproduction")
        except APIError as exc:
            st.error(str(exc))


def data_page(config: dict) -> None:
    upload_tab, browse_tab, provenance_tab = st.tabs(["Import files", "Browse observations", "Source provenance"])
    with upload_tab:
        st.write("Import original MCX exports. Dates are parsed using the explicit source convention; requested and returned dates remain separate.")
        with st.form("import_form"):
            uploads = st.file_uploader("MCX exports · batch import", type=["csv", "xls", "xlsx", "zip"], accept_multiple_files=True)
            date_order = st.selectbox("Numeric source date order", ["mdy", "dmy"], help="MCX exports may encode returned dates as month/day/year. This does not change expiry strings such as 04SEP2026.")
            has_requested_date = st.checkbox("Record a separately requested download date")
            requested_date = st.date_input("Requested download date", value=date.today(), max_value=date.today())
            submitted = st.form_submit_button("Validate and import files", type="primary")
        if submitted:
            if not uploads:
                st.error("Select at least one export to import.")
            else:
                multipart = [("files", (upload.name, upload.getvalue(), upload.type or "application/octet-stream")) for upload in uploads]
                form_data = {"date_order": date_order}
                if has_requested_date:
                    form_data["requested_date"] = requested_date.isoformat()
                try:
                    with st.spinner("Validating records and preserving source hashes…"):
                        result = api("POST", "/api/import", files=multipart, data=form_data)
                    st.session_state["last_import_result"] = result
                    st.session_state["refresh_scope"] = "real"
                    st.rerun()
                except APIError as exc:
                    st.error(str(exc))
        show_result(st.session_state.get("last_import_result"), "imports")
        st.divider()
        st.markdown("### Reproducible demonstration dataset")
        st.caption("Synthetic observations are stored separately. Creating the dataset does not switch your selected mode.")
        if st.button("Generate isolated synthetic dataset"):
            try:
                with st.spinner("Generating the seeded demonstration dataset…"):
                    st.session_state["last_demo_result"] = api("POST", "/api/demo", body={"seed": int(config["seed"])})
                st.session_state["refresh_scope"] = "synthetic"
                st.rerun()
            except APIError as exc:
                st.error(str(exc))
        show_result(st.session_state.get("last_demo_result"), "demo_generation")
    with browse_tab:
        symbol = st.selectbox("Observation symbol", ["All products", *PRODUCTS])
        limit = st.number_input("Maximum displayed rows", 10, 10000, value=500, step=10)
        params = {"mode": config["mode"], "start": config["start"], "end": config["end"], "limit": int(limit)}
        if symbol != "All products":
            params["symbol"] = symbol
        payload = safe_get("/api/data", params=params)
        show_table(records(payload), key="observations", download=True)
        if isinstance(payload, dict):
            with st.expander("Query metadata"):
                st.json({key: value for key, value in payload.items() if key not in ("records", "rows", "data", "items")})
    with provenance_tab:
        show_result(safe_get("/api/imports"), "source_provenance")


def settings_page(config: dict) -> None:
    left, right = st.columns(2)
    with left:
        caption_title("Explicit cost assumptions")
        st.number_input("All-in transaction cost · bps", min_value=0.0, max_value=1000.0,
                        value=float(config["cost_bps"]), step=0.5, key="setting_cost_bps",
                        help="A research assumption, not a verified historical exchange fee schedule.")
        st.number_input("Execution slippage · bps", min_value=0.0, max_value=1000.0,
                        value=float(config["slippage_bps"]), step=0.5, key="setting_slippage_bps")
        st.number_input("Volatility stress multiplier", 0.1, 5.0, value=float(config["volatility_stress"]), step=0.1, key="setting_volatility_stress")
        st.caption("Holding duration, entry/exit delay, capital and liquidity controls are in the sidebar. Every calculation records its assumptions.")
    with right:
        caption_title("Reproducibility and resource limits")
        st.number_input("Random seed", min_value=0, max_value=2**32-1, value=int(config["seed"]), key="setting_seed")
        st.number_input("Simulation paths", min_value=50, max_value=10000, value=int(config["simulations"]), step=50, key="setting_simulations")
        st.number_input("API computation timeout · seconds", min_value=10, max_value=600, value=int(st.session_state.get("preferences", {}).get("request_timeout", 120)), step=10, key="setting_request_timeout")
    st.divider()
    caption_title("Local connection")
    with st.expander("Effective-dated cost components · optional JSON"):
        st.caption('An empty list uses the all-in bps assumption. Each dated schedule can specify brokerage_per_lot, exchange_bps, regulatory_bps, buy_tax_bps, sell_tax_bps, gst_fraction and extra_per_lot. These are explicit research assumptions.')
        fee_text=st.text_area('Cost schedules',value=json.dumps(st.session_state.get('preferences',{}).get('cost_schedule',[]),indent=2),key='fee_schedule_json',height=150)
        if st.button('Apply cost schedules'):
            try:
                schedules=json.loads(fee_text)
                if not isinstance(schedules,list):
                    raise ValueError('Enter a JSON list of schedules')
                # The API remains authoritative for effective dates and bounds.
                api('POST','/api/validate-config',body={**config,'cost_schedule':schedules})
                st.session_state.setdefault('preferences',{})['cost_schedule']=schedules
                st.success('Cost schedule validated and applied for subsequent calculations.')
            except (ValueError,APIError) as exc:
                st.error(str(exc))
    st.text_input("Research API address", value=st.session_state.get("preferences", {}).get("api_url", os.getenv("AURUM_API_URL", "http://127.0.0.1:8000")), key="setting_api_url")
    preferences = st.session_state.setdefault("preferences", {})
    for name in ("cost_bps", "slippage_bps", "volatility_stress", "seed", "simulations", "request_timeout", "api_url"):
        preferences[name] = st.session_state["setting_" + name]
    if st.button("Check API connection"):
        show_result(safe_get("/health"), "health")
    st.markdown("### Deterministic research mode")
    st.write("The analytical workflow runs without an LLM or paid API. Optional language-model integration is not enabled in this interface; no model credentials are collected here.")
    st.caption("Application settings persist for this browser session. Environment variables configure service startup.")


def main() -> None:
    st.set_page_config(page_title="AURUM X · Commodity Intelligence", page_icon="◆", layout="wide", initial_sidebar_state="expanded")
    sync_connection(api_base())
    refresh_mode = st.session_state.pop("refresh_scope", None)
    if refresh_mode:
        st.session_state.pop("metadata_cache", None)
        clear_results()
        st.session_state.get("research_configs", {}).pop(refresh_mode, None)
        for name in ("start", "end", "cutoff"):
            st.session_state.pop(f"{name}_{refresh_mode}", None)
    apply_pending_preset()
    st.markdown(CSS, unsafe_allow_html=True)
    with st.sidebar:
        st.markdown('<div class="brand">AURUM X</div><div class="brand-sub">Commodity research laboratory</div>', unsafe_allow_html=True)
        experience = st.selectbox("Experience", ["Guided Mode", "Research Mode"], key="experience", on_change=change_experience,
                                  help="Both experiences use the same backend calculations. Research Mode exposes every parameter.")
        mode_label = st.selectbox("Data environment", ["Real MCX history", "Synthetic demonstration"], key="mode_label",
                                 format_func=lambda label: "Imported history · unverified" if label == "Real MCX history" else label)
        mode = "synthetic" if mode_label == "Synthetic demonstration" else "real"
        options = GUIDED_PAGES if experience == "Guided Mode" else PAGES
        if st.session_state.get("page") not in options:
            st.session_state["page"] = options[0]
        page = st.selectbox("Workspace", options, key="page")
        if st.button("Refresh data and connection", key="refresh_data", width="stretch"):
            st.session_state.pop("metadata_cache", None)
            clear_results()
        st.caption("Coverage refreshes on interaction after 30 seconds.")
        st.divider()
    summary, contracts = dataset_metadata(mode)
    observe_dataset(mode, summary, contracts)
    with st.sidebar:
        st.caption("API connected" if summary is not None else "API unavailable")
    config = default_config(summary, mode)
    if experience == "Research Mode":
        restore_research_inputs(config)
        config = research_controls(summary, contracts, mode)
        remember_config(config)
    st.markdown('<div class="page-kicker">Autonomous, adversarially verified commodity intelligence</div>', unsafe_allow_html=True)
    if page != "Welcome":
        st.title(page)
        st.caption(DESCRIPTIONS[page])
    for notice in ("preset_notice", "dataset_notice"):
        message = st.session_state.pop(notice, None)
        if message:
            st.info(message)
    if mode == "synthetic":
        st.warning(SYNTHETIC_LABEL)
    else:
        st.caption("IMPORTED UNVERIFIED DATA · Source authenticity is not certified · No brokerage execution")
    if summary is None:
        st.warning("Dataset coverage is unavailable. Check that the research API is running; Settings contains the connection controls.")
    if page == "Profit Survival Map":
        cost_col, slip_col = st.columns(2)
        config["cost_bps"] = cost_col.number_input("Base assumed costs · bps", 0.0, 1000.0, value=float(config["cost_bps"]), step=0.5, key="survival_cost")
        config["slippage_bps"] = slip_col.number_input("Base assumed slippage · bps", 0.0, 1000.0, value=float(config["slippage_bps"]), step=0.5, key="survival_slippage")
    if experience == "Research Mode":
        render_presets(config, api)
    scope_errors = []
    if config["start"] > config["end"]:
        scope_errors.append("The start date must be on or before the end date.")
    if config["start"] > config["cutoff"]:
        scope_errors.append("The information cutoff must be on or after the start date.")
    if config["capital"] <= 0:
        scope_errors.append("The capital limit must be greater than zero.")
    for error in scope_errors:
        st.error(error)
    if scope_errors and experience == "Research Mode" and page not in ("Settings", "Data Management", "Evidence Center", "Contract Genome"):
        return
    st.divider()
    if page == "Welcome":
        welcome(summary, config, navigate)
    elif page == "Guided Investigation":
        config = wizard(summary, contracts, config, api, navigate, show_result)
    elif page == "Learn gold futures":
        learning(api)
    elif page == "Command Center":
        command_center(summary, contracts, config)
    elif page == "Relative Value Explorer":
        st.caption("Analytical normalization does not remove delivery, location or execution basis risk. Inspect the backend decomposition before interpreting a residual.")
        run_engine(page, "/api/analytics", config, "Compare exact contracts")
        if st.button("Scan all six product pairs", key="scan_pairs"):
            with st.spinner("Scanning eligible pair histories…"):
                try:
                    st.session_state["pair_scan"] = (result_key(page,config),api("POST","/api/scan",body=config))
                except APIError as exc:
                    st.session_state.pop("pair_scan", None)
                    st.error(str(exc))
        scan = st.session_state.get("pair_scan")
        if scan and scan[0] == result_key(page,config):
            for comparison in scan[1]:
                with st.expander(" / ".join(comparison["pair"])):
                    show_result(comparison,"scan_"+"_".join(comparison["pair"]))
    elif page == "Futures Curve Laboratory":
        st.caption("The information cutoff selects the historical curve date. Curve-relative carry is an empirical measure; unobserved funding or storage rates are not invented.")
        run_engine(page, "/api/curves", config, "Build historical futures curve")
    elif page == "Mirage Investigation":
        st.caption("Runs the integrated pipeline and saves an Evidence Certificate, including unresolved checks and unsuccessful conclusions.")
        run_engine(page, "/api/investigations", config, "Run Mirage investigation")
    elif page == "Ghost Market":
        st.caption(f"Seed {config['seed']} · {config['simulations']} paths · volatility multiplier {config['volatility_stress']:g}. Positive modeled outcomes are not a calibrated real-world probability of profit.")
        run_engine(page, "/api/ghost", config, "Run Ghost Market", "histogram")
    elif page == "Market Red Team":
        st.caption("A test that cannot be evaluated remains unresolved. A passing statistical check does not establish executable liquidity.")
        run_engine(page, "/api/audit", config, "Run adversarial verification")
    elif page == "Time-Locked Replay":
        replay_page(config)
    elif page == "Profit Survival Map":
        st.caption("The backend recalculates monetary results using actual contract multipliers and integer lots. Change execution, sizing and liquidity assumptions in the sidebar.")
        run_engine(page, "/api/survival", config, "Recalculate survival map", "heatmap")
    elif page == "Anomaly DNA":
        st.caption("Similar historical observations are descriptive evidence. Sparse samples and unavailable forward outcomes remain explicit.")
        run_engine(page, "/api/analogs", config, "Search eligible historical analogs")
    elif page == "Contract Genome":
        specs = safe_get("/api/specifications", {"mode": mode})
        caption_title("Specification registry")
        show_result(specs, "specifications")
        caption_title("Observed contract identities and lifecycle coverage")
        show_table(records(contracts, "contracts"), key="genome_contracts", download=True)
    elif page == "Evidence Center":
        evidence_page(mode)
    elif page == "Data Management":
        data_page(config)
    elif page == "Settings":
        settings_page(config)
    if experience == "Guided Mode" and page != "Welcome":
        render_presets(config, api)
    st.divider()
    st.caption("AURUM X / Research prototype · Evidence certificates record assumptions and limitations. No guaranteed returns or verified execution are implied.")


if __name__ == "__main__":
    main()
