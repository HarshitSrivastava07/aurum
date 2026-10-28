"""Deterministic explanations of backend evidence; no trading recommendations."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from frontend.theme import PALETTE, style_chart


TERMS = {
    "Gold futures": "An exchange-traded agreement for a specified quantity and quality of gold, with a defined expiry and delivery lifecycle.",
    "Margin": "Collateral required to maintain a futures position. It is not the maximum possible loss. This app uses fully funded gross notional, not a margin model.",
    "Expiry": "The end of a contract's trading lifecycle. Tender and delivery restrictions may start earlier.",
    "Basis": "A price difference between related instruments or locations. It may reflect real economic differences.",
    "Carry": "The effect of time to delivery, financing and storage. This app only estimates supported empirical curve differences.",
    "Z-score": "How far a spread is from its earlier average, measured in historical standard deviations. It is not a probability of profit.",
    "Slippage": "The difference between a modeled price and a fill price. Here it is an explicit cost assumption.",
    "Hedge ratio": "The relative size of two positions. Integer lots and different gold purity can leave residual exposure.",
    "Mark-to-market": "Valuing an open position at an observed price. A mark does not prove that a position could be closed at that price.",
    "Liquidity": "The ability to trade at an acceptable price. Daily volume does not establish order-book depth or a two-leg fill.",
    "Drawdown": "A decline from a previous peak in modeled equity. The app's drawdown includes marked open positions.",
    "Walk-forward backtest": "A chronological replay that fits parameters on earlier observations and applies them later. Reusing the same test period weakens independent evidence.",
    "Basis points (bps)": "One basis point is 0.01%. Costs are applied to traded notional at each modeled entry and exit.",
}


def provenance(mode: str) -> str:
    return "SYNTHETIC TEST DATA" if mode == "synthetic" else "IMPORTED UNVERIFIED DATA"


def findings(certificate: dict) -> dict:
    outputs = certificate.get("outputs", {})
    analysis = outputs.get("mirage", {})
    replay = outputs.get("replay", {})
    metrics = replay.get("metrics", {})
    audit = outputs.get("red_team", {}).get("summary", {})
    latest = analysis.get("latest") or {}
    verdict = certificate.get("verdict", "INSUFFICIENT EVIDENCE")
    if verdict == "SURVIVES MODELED TESTS":
        conclusion = "The selected investigation survived its modeled tests. This does not establish live execution or future performance."
    elif verdict == "REJECTED":
        conclusion = "The investigation did not pass the required tests. Inspect the failed checks and cost assumptions before drawing a conclusion."
    else:
        conclusion = "The available evidence is not strong enough to support this research hypothesis. A completed calculation can still leave important questions unresolved."
    if not analysis.get("sessions"):
        discovery = "No usable paired history was available for the selected contracts and period."
    elif latest.get("candidate"):
        discovery = "The latest observed spread met the anomaly and eligibility checks. An unusual spread is a question to investigate, not a trading instruction."
    else:
        discovery = "The latest observed session did not meet all anomaly and eligibility checks. This does not establish that the prices are economically equivalent."
    if metrics.get("trades", 0) and metrics.get("gross_pnl", 0) > 0 and metrics.get("net_pnl", 0) <= 0:
        next_action = "The completed hypothetical trades lost their modeled gross advantage after costs. Inspect the Profit Survival Map."
        destination = "Profit Survival Map"
    elif verdict == "SURVIVES MODELED TESTS":
        next_action = "Review liquidity, source authenticity and delivery restrictions before interpreting this as executable."
        destination = "Market Red Team"
    elif not analysis.get("sessions"):
        next_action = "Import daily observations or select exact contracts with overlapping history."
        destination = "Data Management"
    elif audit.get("fail", 0):
        next_action = "Inspect the failed adversarial checks and their supporting evidence."
        destination = "Market Red Team"
    else:
        next_action = "Inspect unresolved checks and seek more independent history. More reruns of the same period do not add independent evidence."
        destination = "Market Red Team"
    return {"verdict": verdict, "conclusion": conclusion, "discovery": discovery,
            "next_action": next_action, "destination": destination}


def render_summary(certificate: dict, navigate) -> None:
    info = findings(certificate)
    config = certificate.get("config", {})
    outputs = certificate.get("outputs", {})
    analysis = outputs.get("mirage", {})
    replay = outputs.get("replay", {})
    metrics = replay.get("metrics", {})
    latest = analysis.get("latest") or {}

    # Layer 1 — Verdict with visual emphasis
    verdict = info["verdict"]
    st.subheader(f"Verdict: {verdict}")
    with st.container(border=True):
        st.write(info["conclusion"])

    st.write(info["discovery"])
    st.caption(f"{' / '.join(config.get('pair', []))} · {config.get('start')} to {config.get('end')} · cutoff {config.get('cutoff')} · {provenance(config.get('mode', 'real'))}")

    # Layer 2 — Key metrics
    cols = st.columns(4)
    cols[0].metric("Observed paired sessions", analysis.get("sessions", 0))
    cols[1].metric("Completed hypothetical trades", metrics.get("trades", 0))
    cols[2].metric("Execution feasibility", certificate.get("execution_feasibility", "Unverified"))
    audit = outputs.get("red_team", {}).get("summary", {})
    audit_passed = audit.get('pass', 0)
    audit_failed = audit.get('fail', 0)
    audit_unresolved = audit.get('not-evaluable', 0)
    cols[3].metric("Adversarial checks", f"{audit_passed}✓ {audit_failed}✗ {audit_unresolved}?")
    st.caption("Adversarial results are test counts, not confidence probabilities.")

    # Layer 3 — Spread decomposition (visual explanation)
    st.markdown("#### How the price difference changes")
    if latest:
        stages = [
            {"Stage": "Original quoted prices", "First contract": latest.get("price_a"), "Second contract": latest.get("price_b"), "Basis": "INR per each contract's quotation unit; not directly comparable"},
            {"Stage": "After quotation and purity normalization", "First contract": latest.get("normalized_a"), "Second contract": latest.get("normalized_b"), "Basis": "INR per fine gram"},
        ]
        st.dataframe(pd.DataFrame(stages), hide_index=True, width="stretch")
        values = [latest.get("normalized_spread"), latest.get("maturity_component"), latest.get("residual")]
        if all(value is not None for value in values):
            # Waterfall-style decomposition chart
            fig = go.Figure()
            labels = ["Normalized spread", "Maturity component", "Remaining spread"]
            colors = PALETTE[:3]
            for i, (label, val, color) in enumerate(zip(labels, values, colors)):
                fig.add_trace(go.Bar(name=label, x=[label], y=[val], marker_color=color,
                    hovertemplate=f"{label}: ₹%{{y:.4f}} per fine gram<extra></extra>"))
            style_chart(fig, f"Spread components on {latest['date']}", height=340)
            fig.update_layout(yaxis_title="INR per fine gram", showlegend=False, bargap=0.4)
            st.plotly_chart(fig, width="stretch", key="guided_decomposition")
            st.caption(f"Policy {config.get('baseline', 'C')}: A retains maturity basis; B and C subtract a supported curve component. These components do not identify causal profit.")
        else:
            st.info("A supported maturity adjustment is unavailable. The remaining spread retains unresolved expiry basis; no value is invented.")
    else:
        st.info("A price decomposition needs overlapping, valid observations for the selected exact contracts.")

    # Layer 4 — P&L with cost impact
    st.markdown("#### Hypothetical financial outcome")
    cost_cols = st.columns(3)
    gross = metrics.get("gross_pnl", 0)
    costs = metrics.get("costs", 0)
    net = metrics.get("net_pnl", 0)
    cost_cols[0].metric("Gross modeled P&L · INR", f"₹{gross:,.2f}")
    cost_cols[1].metric("Modeled trading costs · INR", f"₹{costs:,.2f}")
    cost_cols[2].metric("Net modeled P&L · INR", f"₹{net:,.2f}",
                        delta=f"{'Profitable' if net > 0 else 'Loss'} after costs" if metrics.get("trades", 0) else None,
                        delta_color="normal" if net > 0 else "inverse")
    st.caption("P&L totals refer to completed hypothetical trades over the period, not the latest per-gram spread. Zero trades provide no evidence of profitability.")
    if replay.get("open_position"):
        st.warning("A position remains unresolved. Completed-trade P&L excludes its unrealized mark; inspect the replay before interpreting totals.")

    # Layer 5 — Risks and limitations
    with st.expander("Main risks and evidence limitations", expanded=True):
        risks = list(dict.fromkeys([*analysis.get("warnings", []), *replay.get("warnings", []), *certificate.get("limitations", [])]))
        for risk in risks[:8]:
            st.write(f"• {risk}")

    # Layer 6 — Next action with styled container
    st.markdown("#### What to investigate next")
    with st.container(border=True):
        st.write(info["next_action"])
        action_cols = st.columns(2)
        action_cols[0].button("Open supporting workspace", on_click=navigate, args=(info["destination"],), key="guided_next_action", type="primary", width="stretch")
        action_cols[1].button("Open saved evidence", on_click=navigate, args=("Evidence Center",), key="guided_open_evidence", width="stretch")


def glossary() -> None:
    term = st.selectbox("Explain a research term", list(TERMS), key="help_term")
    st.info(TERMS[term])
