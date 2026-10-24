"""A guided client for the same deterministic research API used by experts."""
from __future__ import annotations

from datetime import date
import json

import pandas as pd
import streamlit as st

from frontend.explanations import glossary, provenance, render_summary
from frontend.workspace import remember_config


STEPS = ["Question", "Contracts", "Period", "Review", "Run", "Results", "Explore deeper"]
QUESTIONS = {
    "Why do two gold contracts have different prices?": ("mirage", "Relative Value Explorer"),
    "Were there unusual differences in a historical period?": ("mirage", "Relative Value Explorer"),
    "Did a historical strategy survive modeled costs?": ("replay", "Profit Survival Map"),
    "How risky is a particular price difference?": ("ghost", "Ghost Market"),
    "Explore an educational example": ("education", "Learn gold futures"),
}
PRODUCT_NAMES = {"GOLDM": "Gold Mini", "GOLDTEN": "Gold Ten", "GOLDGUINEA": "Gold Guinea", "GOLDPETAL": "Gold Petal"}


def contract_rows(contracts):
    if isinstance(contracts, list):
        return contracts
    return (contracts or {}).get("contracts", [])


def _step(step: int) -> None:
    st.session_state["guided_step"] = step


def welcome(summary, config, navigate) -> None:
    st.title("Understand gold futures. Test the evidence.")
    st.markdown("""<div style="text-align:center; padding:0.5rem 0 0.8rem;">
        <div style="font-size:2.8rem; font-weight:700; letter-spacing:-0.04rem; color:#E5CD9D;">AURUM X</div>
        <div style="font-size:1.1rem; color:#A8B2BF; margin-top:0.3rem; letter-spacing:0.08rem;">
            Investigate Price Differences · Test the Evidence
        </div>
    </div>""", unsafe_allow_html=True)

    st.markdown("""<div style="text-align:center; padding:0 2rem 1.5rem; max-width:700px; margin:0 auto;">
        <p style="color:#CED3DB; font-size:0.95rem; line-height:1.65;">
            Gold futures contracts can trade at different prices because of purity, contract size,
            expiry and market conditions. AURUM X investigates these differences to determine whether
            they are normal, unusual, or potentially meaningful after costs and risks.
        </p>
    </div>""", unsafe_allow_html=True)

    columns = st.columns(3, gap="medium")
    choices = [
        ("🔍  Start Guided Investigation",
         "Choose a research question and follow the evidence step by step. No manual configuration required.",
         "Guided Investigation", None, "primary"),
        ("📊  Explore a Demonstration",
         "Learn the complete workflow using reproducible, clearly labeled synthetic prices.",
         "Guided Investigation", "synthetic", "secondary"),
        ("⚙️  Open Research Workspace",
         "Full analytical control with exact contracts, detailed parameters and every research engine.",
         "Command Center", None, "secondary"),
    ]
    for column, (label, explanation, page, mode, btn_type) in zip(columns, choices):
        with column, st.container(border=True):
            st.markdown(f"<div style='min-height:4.5rem;'>{explanation}</div>", unsafe_allow_html=True)
            st.button(label, on_click=navigate, args=(page, mode), key=f"welcome_{page}_{mode}",
                      type=btn_type, width="stretch")

    st.divider()

    # Visual research pipeline
    st.markdown("#### How an investigation works")
    pipeline_cols = st.columns(5, gap="small")
    pipeline_steps = [
        ("📥", "Market Data", "Load and validate daily contract prices"),
        ("⚖️", "Normalization", "Adjust for purity, units and contract differences"),
        ("🔎", "Anomaly Detection", "Find unusual price differences using statistical methods"),
        ("🛡️", "Risk Testing", "Challenge findings with costs, stress and adversarial checks"),
        ("📋", "Evidence Verdict", "Preserve the investigation with a clear conclusion"),
    ]
    for col, (icon, title, desc) in zip(pipeline_cols, pipeline_steps):
        with col:
            st.markdown(f"""<div style="text-align:center; padding:0.6rem 0.3rem;
                border:1px solid #29303A; border-radius:8px; background:#131921; min-height:8rem;">
                <div style="font-size:1.5rem;">{icon}</div>
                <div style="font-size:0.82rem; font-weight:600; color:#E5CD9D; margin:0.3rem 0 0.2rem;">{title}</div>
                <div style="font-size:0.72rem; color:#A8B2BF;">{desc}</div>
            </div>""", unsafe_allow_html=True)
    st.caption("A completed investigation may reject an idea or find insufficient evidence. Both are useful research outcomes.")

    # Workspace status
    st.markdown("#### Your workspace")
    status_cols = st.columns(4)
    status_cols[0].metric("Backend", "Connected" if summary is not None else "Unavailable")
    status_cols[1].metric("Daily observations", (summary or {}).get("rows", (summary or {}).get("row_count", 0)))
    status_cols[2].metric("Active investigation", "Running" if st.session_state.get("guided_job") else "None")
    status_cols[3].metric("Data mode", "Synthetic" if config["mode"] == "synthetic" else "Real MCX")
    st.write(f"**Data provenance:** {provenance(config['mode'])}")
    imports = (summary or {}).get("imports", [])
    if imports:
        st.caption(f"Latest recorded import: {imports[0].get('timestamp', 'Unavailable')}. Source authenticity has not been independently verified.")
    else:
        st.caption("No verified real-market import is available. Use the demonstration or import original daily files.")
    with st.expander("New to gold futures?"):
        glossary()
        st.button("Open the interactive learning example", on_click=navigate, args=("Learn gold futures",), key="welcome_learn")



def learning(api) -> None:
    st.markdown("""Gold futures contracts trade on MCX with different specifications.
    Understanding these differences is essential before comparing prices.""")

    with st.expander("Essential gold futures concepts", expanded=True):
        glossary()

    st.markdown("#### Why do two gold contracts have different prices?")
    st.markdown("""Different gold futures differ in **purity** (995 vs 999 fineness),
    **contract size** (1g to 100g lots), **expiry date**, **delivery terms** and **market liquidity**.
    A direct price comparison without accounting for these differences is misleading.""")

    st.markdown("#### Interactive purity comparison")
    st.caption("EDUCATIONAL EXAMPLE · invented inputs, not market observations. Assumptions: GOLDM 995 purity, GOLDTEN 999 purity, both quoted per 10 g.")
    with st.form("education_form"):
        first, second = st.columns(2)
        a = first.number_input("Hypothetical GOLDM quote · INR per 10 g", min_value=0.01, max_value=1e9, value=100000.0, step=100.0, key="education_a",
                               help="GOLDM has 995 purity (99.5% fine gold). 100g trading unit, quoted per 10g.")
        b = second.number_input("Hypothetical GOLDTEN quote · INR per 10 g", min_value=0.01, max_value=1e9, value=101000.0, step=100.0, key="education_b",
                                help="GOLDTEN has 999 purity (99.9% fine gold). 10g trading unit, quoted per 10g.")
        submitted = st.form_submit_button("Compare hypothetical quotations", type="primary")
    if submitted:
        try:
            st.session_state["education_result"] = api("POST", "/api/education/compare", body={"goldm_quote": a, "goldten_quote": b})
        except RuntimeError as exc:
            st.session_state.pop("education_result", None)
            st.error(str(exc))
    result = st.session_state.get("education_result")
    if result:
        if "goldm" in result and "goldten" in result:
            st.markdown("##### Step 1 — Original vs. purity-adjusted prices")
            st.dataframe(pd.DataFrame([
                {"Comparison": "Original quote · INR per 10 g", "GOLDM": result["goldm"]["original_per_10g"], "GOLDTEN": result["goldten"]["original_per_10g"]},
                {"Comparison": "Equivalent 999-purity quote · INR per 10 g", "GOLDM": result["goldm"]["purity_adjusted_per_10g"], "GOLDTEN": result["goldten"]["purity_adjusted_per_10g"]},
            ]), hide_index=True, width="stretch")
            st.markdown("##### Step 2 — Remaining difference after purity adjustment")
            st.metric("Remaining hypothetical difference · INR per 10 g", f"₹{result['difference']:,.2f}")
            st.caption(result["difference_direction"])
            st.write(f"**Formula:** {result['formula']}")
        with st.expander("Full calculation details and assumptions"):
            st.json(result, expanded=2)
    st.info("A remaining price difference is not automatically profit. Expiry, financing, delivery terms, location, liquidity and trading costs still matter.")


@st.fragment(run_every="1s")
def job_progress(api) -> None:
    STAGE_HINTS = {
        "snapshot": "Freezing the dataset so results are reproducible…",
        "mirage": "Normalizing prices and detecting unusual spread differences…",
        "curves": "Inspecting historical futures curve shape…",
        "analogs": "Searching for similar historical episodes…",
        "replay": "Replaying hypothetical trades chronologically with costs…",
        "red_team": "Running adversarial checks against the findings…",
        "ghost": "Simulating adverse market scenarios…",
        "survival": "Testing whether costs and delays eliminate the signal…",
        "baseline_comparison": "Comparing research policies for robustness…",
        "certificate": "Preserving the evidence certificate…",
    }
    STATUS_ICONS = {"pending": "⏳", "running": "🔄", "completed": "✅", "warning": "⚠️", "skipped": "⏭️", "failed": "❌"}

    job_ref = st.session_state.get("guided_job")
    if not job_ref:
        return
    try:
        job = api("GET", f"/api/investigation-jobs/{job_ref['id']}")
    except RuntimeError as exc:
        st.error(str(exc))
        st.caption("Progress is unavailable. The backend may still be working. Reconnect before submitting another investigation; saved certificates remain in Evidence Center.")
        if st.button("Check status again", key="job_retry"):
            st.rerun(scope="fragment")
        return

    stages = job.get("stages", [])
    completed = sum(stage["status"] in ("completed", "warning", "skipped") for stage in stages)
    running_stage = next((s for s in stages if s["status"] == "running"), None)

    # Show current activity
    if running_stage:
        stage_name = running_stage.get("name", "")
        hint = STAGE_HINTS.get(stage_name, running_stage.get("label", "Processing…"))
        st.info(f"🔄 **{running_stage.get('label', stage_name)}** — {hint}")

    st.progress(completed / max(1, len(stages)), text=f"{completed} of {len(stages)} stages complete")

    # Enhanced stage table with icons
    stage_rows = []
    for stage in stages:
        icon = STATUS_ICONS.get(stage.get("status", "pending"), "·")
        stage_rows.append({
            "": icon,
            "Stage": stage.get("label", stage.get("name", "Unknown")),
            "Status": stage.get("status", "pending"),
            "Detail": stage.get("message", ""),
        })
    st.dataframe(pd.DataFrame(stage_rows), hide_index=True, width="stretch")
    st.caption("Progress comes from the backend. Cancellation takes effect between stages; the current calculation is allowed to finish safely.")
    if job.get("can_cancel") and st.button("Cancel investigation", key="cancel_guided_job"):
        try:
            api("POST", f"/api/investigation-jobs/{job['id']}/cancel")
            st.rerun(scope="fragment")
        except RuntimeError as exc:
            st.error(str(exc))
    if job["status"] == "completed":
        st.session_state["guided_result"] = job["result"]
        st.session_state["guided_completed_stages"] = stages
        st.session_state.pop("guided_job", None)
        _step(5)
        st.rerun()
    elif job["status"] in ("failed", "cancelled"):
        error = job.get("error") or {}
        st.error(error.get("message") or "The investigation was cancelled before completing all stages.")
        if st.button("Return to configuration", key="job_recover"):
            st.session_state.pop("guided_job", None)
            _step(3)
            st.rerun()


def _contract_details(row: dict, name: str) -> None:
    spec = row.get("spec") or {}
    st.markdown(f"**{name} · {row.get('expiry', 'Unknown expiry')}**")
    st.caption(f"Observed {row.get('first_observed', 'unknown')} to {row.get('last_observed', 'unknown')} · {row.get('sessions', 'unknown')} sessions")
    if spec:
        st.write(f"Trading unit: {spec.get('trading_unit_g', 'unknown')} g · Quotation unit: {spec.get('quotation_unit_g', 'unknown')} g · Purity: {spec.get('purity', 'unknown')}")
        st.caption(f"Delivery/quotation location: {spec.get('quote_location', 'unverified')}. Specification ID: {spec.get('spec_id', 'unavailable')}.")
    lifecycle = row.get("lifecycle") or {}
    st.caption(f"Tender boundary: {lifecycle.get('tender_start') or 'not verified'}. Listing date: {row.get('listing_date') or 'not verified'}.")
    if not spec.get("verified"):
        st.caption("Historical specification authenticity is unverified; real execution remains blocked.")


def wizard(summary, contracts, config, api, navigate, show_result) -> dict:
    step = st.session_state.get("guided_step", 0)
    if st.session_state.get("guided_job"):
        step = 4
    st.caption(f"Step {step + 1} of {len(STEPS)} · {STEPS[step]}")
    st.write(" → ".join(STEPS))
    ready = True
    if step == 0:
        st.subheader("What would you like to investigate?")
        st.radio("Choose your research question", list(QUESTIONS), key="guided_question")
        st.caption("Every research question runs the same complete investigation. Your choice selects which evidence to explore next.")
        if st.session_state.get("guided_question") == "Explore an educational example":
            st.button("Open learning example", on_click=navigate, args=("Learn gold futures",), key="wizard_education")
            ready = False
    elif step == 1:
        st.subheader("Choose two observed contracts")
        rows = contract_rows(contracts)
        symbols = sorted({row["symbol"] for row in rows if row.get("symbol") in PRODUCT_NAMES})
        if len(symbols) < 2:
            ready = False
            st.info("This data environment needs daily observations for at least two supported products. Imported annual totals cannot supply contract history.")
            st.button("Open data management", on_click=navigate, args=("Data Management",), key="wizard_import")
            if config["mode"] == "real":
                st.button("Use the synthetic demonstration", on_click=navigate, args=("Guided Investigation", "synthetic"), key="wizard_demo")
            elif st.button("Generate demonstration data", key="wizard_generate"):
                try:
                    api("POST", "/api/demo", body={"seed": int(config["seed"])})
                    st.session_state["refresh_scope"] = "synthetic"
                    st.rerun()
                except RuntimeError as exc:
                    st.error(str(exc))
        else:
            first = st.selectbox("First gold product", symbols, index=symbols.index(config["pair"][0]) if config["pair"][0] in symbols else 0,
                                 format_func=lambda x: f"{x} · {PRODUCT_NAMES[x]}", key="guide_input_pair_a")
            choices = [s for s in symbols if s != first]
            second = st.selectbox("Second gold product", choices, index=choices.index(config["pair"][1]) if config["pair"][1] in choices else 0,
                                  format_func=lambda x: f"{x} · {PRODUCT_NAMES[x]}", key=f"guide_input_pair_b_{first}")
            config["pair"] = [first, second]
            selected = []
            for column, leg, symbol in zip(st.columns(2), ("a", "b"), config["pair"]):
                with column:
                    options = sorted({row["expiry"] for row in rows if row.get("symbol") == symbol})
                    prior = config.get(f"expiry_{leg}")
                    expiry = st.selectbox(f"{symbol} expiry", options, index=options.index(prior) if prior in options else 0,
                                          key=f"guide_input_expiry_{config['mode']}_{leg}_{symbol}")
                    config[f"expiry_{leg}"] = expiry
                    row = next(r for r in rows if r.get("symbol") == symbol and r.get("expiry") == expiry)
                    selected.append(row)
                    _contract_details(row, symbol)
            boundaries = [(r.get("first_observed"), r.get("last_observed")) for r in selected]
            if all(a and b for a, b in boundaries):
                start, end = max(a for a, _ in boundaries), min(b for _, b in boundaries)
                if start > end:
                    st.error("These exact contracts have no overlapping observed period. Choose other expiries.")
                    ready = False
                else:
                    st.session_state["guided_coverage"] = {"pair": config["pair"], "expiry_a": config["expiry_a"], "expiry_b": config["expiry_b"], "start": start, "end": end}
                    st.caption(f"Available overlapping coverage: {start} to {end}. Individual missing sessions remain excluded.")
    elif step == 2:
        st.subheader("Choose a historical period")
        coverage = st.session_state.get("guided_coverage", {})
        st.caption(f"Observed overlap: {coverage.get('start', 'unknown')} to {coverage.get('end', 'unknown')}. Use at least {config['window'] + 1} paired sessions for the rolling baseline; robust evaluation needs substantially more.")
        if st.button("Use available overlapping period", key="guide_use_coverage", disabled=not coverage):
            for name in ("start", "end", "cutoff"):
                value = coverage["start" if name == "start" else "end"]
                config[name] = value
                st.session_state[f"guide_input_{name}_{config['mode']}"] = date.fromisoformat(value)
        for column, name, label in zip(st.columns(3), ("start", "end", "cutoff"), ("First session", "Last session", "Information cutoff")):
            config[name] = column.date_input(label, value=date.fromisoformat(config[name]), min_value=date.min, max_value=date.today(),
                                            key=f"guide_input_{name}_{config['mode']}", help="No observations after the cutoff can enter fitted statistics or decisions.").isoformat()
        if config["start"] > min(config["end"], config["cutoff"]):
            st.error("The first session must be on or before both the last session and the information cutoff.")
            ready = False
        if coverage and (config["start"] < coverage["start"] or min(config["end"], config["cutoff"]) > coverage["end"]):
            st.warning("Your period extends outside the observed contract overlap. Only available observed sessions can be used; missing history is not filled.")
    elif step == 3:
        st.subheader("Review your investigation")
        st.write(f"Compare **{config['pair'][0]} / {config['pair'][1]}** from **{config['start']}** through **{config['end']}**, using information available by **{config['cutoff']}**.")
        st.write(f"Exact expiries: {config.get('expiry_a', 'automatic')} / {config.get('expiry_b', 'automatic')}.")
        st.write(f"Data: **{provenance(config['mode'])}**. The investigation adjusts supported contract differences, checks earlier history and tests costs, lifecycle and execution assumptions.")
        with st.expander("Advanced research assumptions"):
            config["window"] = st.number_input("Prior baseline · sessions", 5, 252, value=int(config["window"]), key="guide_input_window", help="Statistics use earlier sessions only.")
            config["baseline"] = st.selectbox("Research policy", ["C", "B", "A"], index=["C", "B", "A"].index(config["baseline"]), key="guide_input_baseline",
                                             help="C applies full prospective gates; A and B are simpler reference policies.")
            config["cost_bps"] = st.number_input("Trading costs · bps", 0.0, 1000.0, value=float(config["cost_bps"]), key="guide_input_cost", help="One bps is 0.01% of traded notional per side.")
            config["slippage_bps"] = st.number_input("Slippage · bps", 0.0, 1000.0, value=float(config["slippage_bps"]), key="guide_input_slip")
            st.session_state.setdefault("preferences", {}).update(cost_bps=config["cost_bps"], slippage_bps=config["slippage_bps"])
            st.session_state.setdefault("preferences", {}).update(cost_bps=config["cost_bps"], slippage_bps=config["slippage_bps"])
            st.caption(f"Capital: INR {config['capital']:,.2f}, max lots: {config['max_lots']}, holding: {config['holding_days']} sessions, delay: {config['execution_delay']} sessions. Research Mode exposes every setting; these same values are passed to the API.")
            st.json(config, expanded=False)
        st.info("Daily prices do not prove that both legs could have filled. AURUM X has no brokerage connection and no live margin model.")
        if config["start"] > min(config["end"], config["cutoff"]):
            st.error("The period is invalid. Return to the period step.")
            ready = False
    elif step == 4:
        st.subheader("Run and follow the investigation")
        if st.session_state.get("guided_job"):
            job_progress(api)
        else:
            st.caption("The backend will preserve a dataset snapshot, run all research engines and save an evidence certificate. A completed stage can include warnings or insufficient evidence.")
            if st.button("Run guided investigation", type="primary", key="guided_run"):
                try:
                    job = api("POST", "/api/investigation-jobs", body=config)
                    st.session_state["guided_job"] = {"id": job["id"], "config": dict(config)}
                    st.session_state.pop("guided_result", None)
                    st.rerun()
                except RuntimeError as exc:
                    st.error(str(exc))
        ready = False
    elif step == 5:
        result = st.session_state.get("guided_result")
        if result:
            render_summary(result, navigate)
            st.download_button("Download investigation certificate", json.dumps(result, indent=2, default=str),
                               file_name=f"aurum-x-{result['id']}.json", mime="application/json", key="guided_download")
            with st.expander("Supporting evidence and research details"):
                show_result(result, "guided_evidence")
            with st.expander("Completed investigation timeline"):
                st.dataframe(st.session_state.get("guided_completed_stages", []), hide_index=True, width="stretch")
        else:
            st.info("Run an investigation to see its evidence. Refreshing data clears live results; preserved certificates remain in Evidence Center.")
            ready = False
            st.button("Return to review", on_click=_step, args=(3,), key="guided_missing_result")
    elif step == 6:
        st.subheader("Choose your next question")
        question = st.session_state.get("guided_question", next(iter(QUESTIONS)))
        _, destination = QUESTIONS[question]
        st.write(f"Your question: {question}")
        st.button("Explore the relevant research workspace", on_click=navigate, args=(destination,), key="guided_deeper")
        st.button("Inspect the preserved certificate", on_click=navigate, args=("Evidence Center",), key="guided_certificate")
        st.button("Start another guided investigation", on_click=_step, args=(0,), key="guided_restart")
        ready = False
    remember_config(config)
    back, forward = st.columns(2)
    back.button("Previous step", disabled=step == 0 or bool(st.session_state.get("guided_job")), on_click=_step, args=(max(0, step - 1),), key="guided_back")
    forward.button("Continue", disabled=not ready or step >= len(STEPS) - 1, on_click=_step, args=(min(len(STEPS) - 1, step + 1),), key="guided_continue")
    return config
