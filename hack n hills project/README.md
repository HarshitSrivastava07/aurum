# AURUM X

**Autonomous, adversarially verified commodity intelligence.** A local FastAPI + Streamlit research prototype for MCX gold futures, built for Hack in Hills 2026, Track 03.

The application has working data ingestion, a versioned Contract Genome, relative-value and curve analytics, joint scenario simulation, adversarial checks, chronological replay, sensitivity analysis, historical analog search, an experiment ledger, and reproducible JSON evidence certificates. It uses no paid API or LLM and has no brokerage/order execution.

**The five supplied files are annual trading-statistics exports, not daily Bhavcopy history.** Their hashes and rejection reports are preserved. They supply **zero daily prices and zero expiry-specific histories**. Real-mode historical results remain unavailable. Files (2) and (3) are identical. See [source inspection](docs/data_sources.md).

## Run on Windows

From this directory, with Python 3.11+ installed:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
powershell -ExecutionPolicy Bypass -File scripts\start.ps1
```

The existing `.venv` in this workspace was installed and tested using bundled Python 3.12.14, because the system `py` launcher had no registered Python. You can run the final command immediately on this machine. The script starts a hidden backend, runs Streamlit in the foreground, and stops its backend on exit. Do not start a second backend on the same port. Open **http://127.0.0.1:8501**. API documentation: **http://127.0.0.1:8000/docs**. Health check: **http://127.0.0.1:8000/health**.

Alternatively, use two terminals:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
.\.venv\Scripts\python.exe -m streamlit run frontend/app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true
```

Use **one API worker**, because DuckDB is local storage. Configuration comes from process environment variables in `.env.example`; this file is a reference, not an automatically loaded secret file. `AURUM_DATA_DIR`, `AURUM_EVIDENCE_DIR`, and `AURUM_API_URL` have local defaults. Settings in the UI persist within the browser session; each certificate preserves its complete research configuration.

## Workspace improvements

- Use the **Workspace** selector and Command Center shortcuts to navigate. Empty datasets offer direct links to the synthetic demonstration and market-data import.
- Open **Research presets** to save named settings, load them later in the session, or download/import a portable JSON preset. Saving and importing validate against the API. Presets preserve the data mode, pair, exact expiries, dates, costs and execution assumptions. Download presets to keep them after closing the session; up to 20 can be saved per session.
- Every engine result has a **Download result · JSON** action containing the submitted configuration and returned evidence.
- Coverage is reused for 30 seconds between interactions. **Refresh data and connection** fetches fresh coverage and clears live results. Imports, demo generation and connection changes also invalidate old results; preserved evidence certificates remain available.
- Replay loads distinct observed dates through `/api/sessions`, so sessions are not lost to the observation table's row limit.
- Imports process outside the API event loop. Malformed spreadsheet and CSV files return per-file rejection reports, allowing valid files in the same batch to continue.

Buttons use standard controls with descriptive labels. No decorative animation is added.

## Demonstrate the complete workflow

1. Open **Data Management → Source provenance** to see the five supplied files, their hashes, the duplicate 2023 report, and `annual_aggregate` rejections.
2. Under **Import files**, upload genuine daily MCX CSV/XLS/XLSX/ZIP exports when available. Choose the explicit returned-date convention. The [official Bhavcopy page](https://www.mcxindia.com/market-data/bhavcopy) is the manual source; automated downloading is not claimed to work.
3. For the complete local demonstration, use **Generate isolated synthetic dataset**, seed 42. In this delivered workspace it is already generated. Select **Synthetic demonstration** in the sidebar. A persistent warning distinguishes every synthetic screen.
4. Use GOLDM/GOLDTEN, 2025-01-02 through 2025-09-10, window 20, seed 42, costs 5 bps, slippage 2 bps. Each product has three fictional expiry identities; automatic replay selection freezes one pair at the first decision session.
5. **Relative Value Explorer** compares exact expiries or scans all six product pairs. **Futures Curve Laboratory** shows the first selected product's curve at the cutoff.
6. **Command Center → Run full investigation** executes the full pipeline. PolicyC imposes robust-score, lifecycle, geographic, maturity and prospective bootstrap gates. It may reject every trade. That is a valid demonstration, not a missing success state. Choose policy B or A to inspect the simpler baselines. The full investigation also reports all three on identical periods and execution assumptions.
7. **Ghost Market**, **Market Red Team**, **Anomaly DNA**, and **Profit Survival Map** can run separately. Changing assumptions invalidates the displayed result until recalculated. Ghost distributions display the first100 paths; their summaries use every simulated path.
8. **Time-Locked Replay** loads observed sessions and advances the historical cutoff one session at a time. No next-session Open is substituted with Close. Missing exits remain unresolved positions.
9. In **Evidence Center**, select a saved investigation, inspect calculations and the ledger, export JSON, and **Reproduce preserved investigation**. Matching hashes establish deterministic reproduction of that snapshot and version. They do not make local files tamper-proof.

For a scripted demo, stop the API first to avoid cross-process DuckDB contention:

```powershell
.\.venv\Scripts\python.exe scripts\demo.py
```

The synthetic generator plants temporary residual shocks, persistent adverse widening, and thin-liquidity sessions in dependent contract prices. It is a software-validation dataset, not MCX history or evidence of investment returns.

## Architecture and calculations

| Component | Implementation |
|---|---|
| FastAPI boundary | `backend/main.py`; validated and bounded Pydantic requests, upload limits, UUID artifact access, structured request logs |
| Data | `ingestion.py`, `storage.py`; CSV/TSV/XLS/XLSX/HTML-XLS/ZIP, explicit dates, duplicate/conflict handling, immutable raw hashes, DuckDB and Parquet |
| Contract Genome | `genome.py`, `data/specifications/`; expiry-effective versions, unit/purity/location rules, integer sizing and lifecycle gates |
| Mirage | `analytics.py`; six pairs, exact expiry identities, shifted rolling Z/MAD, supported curve-relative maturity adjustment |
| Curve laboratory | Same-product calendar spreads, interpolation without extrapolation, unchanged-contract movement, modeled roll-down and residual shift |
| Ghost Market | `scenarios.py`; jointly sampled paired return blocks, fixed seeds, eleven scenario classes, tail summaries and cost sensitivity |
| Market Red Team | `red_team.py`; 21 executable invariants with pass/fail/not-evaluable, procedures and evidence |
| Replay | `replay.py`; delayed Open proxies, integer holdings, lifecycle checks, prior-volume sizing, costed marks, walk-forward thresholds and frozen final-period parameters |
| Profit Survival | Historical replay reruns across cost/delay grids, holding/slippage/liquidity/exit slices, conditional break-even rates and separate volatility scenarios |
| Anomaly DNA | `analogs.py`; robust-scaled feature distances, non-overlapping analog horizons, outcomes strictly before the query cutoff |
| Research integrity | `ledger.py`, `orchestration.py`; staged typed results, SQLite experiment ledger, snapshot Parquet, configuration/specification/code hashes, JSON certificates |
| Frontend | `frontend/app.py`; 13 workspaces, Plotly, actual backend requests and inspectable results |

Analytical prices are **INR per fine gram**:

```text
quote_base_price = quoted_price / quotation_unit_grams
fine_gram_price  = quoted_price / (quotation_unit_grams × purity_fraction)
common_10g_999   = fine_gram_price × 9.99
leg_P&L         = signed_integer_lots × trading_unit_grams / quotation_unit_grams × (exit_quote − entry_quote)
net_P&L         = sum(leg_P&L) − all entry/exit costs
```

For example, GOLDM quoted at₹99,500 per10g, .995 purity, normalizes to₹10,000 per fine gram; one100g lot is₹995,000. A₹100 quote rise on two GOLDM lots earns₹2,000 gross. One GOLDM versus ten GOLDTEN lots leaves−0.4 fine grams of exposure. These are independent numerical tests, not historical observations.

Default fees are explicit all-in bps assumptions. Optional non-overlapping dated schedules support per-lot brokerage, exchange/regulatory bps, buy/sell taxes, GST fraction on specified fees, extra per-lot penalties, and separate slippage. Configure them in Settings or `/docs`. They are never automatically labeled official. See [methodology and limitations](docs/methodology.md).

## Validation and deployment

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
```

Tests exercise independent monetary fixtures, Hypothesis-generated P&L symmetry, strict dates, unsafe archives, version changes, lifecycle blocks, future/holdout mutations, same-day fill defects, missing opens, joint-bootstrap dependence, sensitivity changes, analog cutoffs, evidence reproduction, snapshot tampering, and all 13 Streamlit pages. UI boundary tests mock HTTP; integration tests use actual FastAPI/storage/engines. See [validation report](docs/validation.md) for executed results and live-browser checks.

Tests use temporary data and evidence directories, so they can run while the local app is open without touching its research database. Additional regressions cover preset round trips, invalid uploads, metadata refresh, failed recalculations and replay-session completeness.

Docker configuration is included:

```powershell
docker compose up --build
```

It exposes only localhost ports 8000/8501 and uses separate persistent data/evidence volumes. **Docker execution has not been verified in this environment**; no Docker executable was available. `requirements.lock` pins the packages actually installed in the Windows environment; the Dockerfile installs the compatible ranges in `pyproject.toml`.

## Current limits and next work

- Real daily-history evaluation is blocked by the supplied dataset's granularity. Import daily contract-wise observations; do not reinterpret yearly totals.
- Official PDFs were read through the browser/search service, but direct retrieval returned 403, so original document hashes remain unavailable. Real execution is blocked by unverified specification provenance, listing calendars and actual tender boundaries. GOLDPETAL's Mumbai basis differs from the Ahmedabad basis of the other selected products.
- Daily prices and volume/OI are imperfect liquidity proxies. No actual two-leg fill, margin model, brokerage connection or executable arbitrage is established.
- Carry uses empirical curve interpolation. Funding, storage, taxes and geographic adjustments are not invented. Attribution is an accounting decomposition, not an independently identified causal return model.
- Final-period parameters are frozen within a run. Subsequent experiments are recorded and flag sample reuse; the software cannot prove the absence of external data snooping.
- Bootstrap tails and analog frequencies are descriptive. Cointegration, calibrated predictive probabilities, causal attribution and statistical performance guarantees are not implemented.
- The optional language-model assistant is not implemented. Every deterministic feature works without it. Long calculations use a spinner and bounded inputs; a persistent job queue, fine-grained cancellation and progress percentages are not implemented.
- Priorities: obtain daily history and official lifecycle calendars; complete historical source hashes/fees; independently review the research methods; expand untouched multi-period validation and improve long-job cancellation.
