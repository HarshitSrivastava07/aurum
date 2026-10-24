        # Executed validation — 9 October 2026

This report distinguishes software verification from financial validation on authentic historical data. There is **no demonstrated real MCX trading edge**: the supplied files contain annual activity totals and no daily prices.

## Runtime and automated checks

Environment: Windows, bundled Python 3.12.14, project-local `.venv`, dependency pins in `requirements.lock`. The system `py` launcher initially reported no installed Python. Installation succeeded from `https://pypi.org/simple` after the initially configured index could not resolve.

Executed final regression command:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --tb=short --basetemp="C:\hack n hills project\logs\test-runtime-final84" -o cache_dir="C:\hack n hills project\logs\test-cache-final84"
```

**84 passed, 0 failed, 0 skipped; 35.86 seconds.** One upstream Starlette TestClient deprecation warning recommends migrating from its httpx adapter to httpx2. It did not affect the executed tests. `python -m pip check` reported **No broken requirements found**. Fresh temporary/cache directories avoid permission errors in directories created under the earlier sandbox user; no application assertions failed in that interrupted run.

Earlier execution identified a real Parquet export defect: DuckDB's positional COPY parameters could bind the destination before SELECT parameters. It was fixed using an Arrow table and the Parquet writer. A separate review identified a holdout boundary that moved as a replay cutoff advanced. It now derives from the declared calendar period; a prefix-invariance test checks that earlier decisions/equity stay identical when more sessions are revealed. Tests were rerun after both fixes.

Final independent review added six regression tests. Survival cells now require resolved positions and positive total equity, so profitable completed trades cannot conceal an open loss. Common percentage shocks use signed monetary exposure, not residual metal grams, to choose the adverse direction. Certificates require all eleven stress classes with eligible lifecycle/liquidity results; a failed audit takes precedence over missing evidence. Snapshot-only audits use explicitly labeled, temporary two-leg future probes when no withheld rows exist, with a positive control proving that a relaxed cutoff sees them. These probes never enter market snapshots or research outcomes. If either contract has expired, the probe remains not-evaluable rather than generating a false leakage failure.

| Area | Executed verification |
|---|---|
| Ingestion | Strict MDY/DMY, expiry strings, padded symbols, unexpected returned dates, annual HTML-XLS rejection, missing/invalid fields, negative or fractional liquidity, duplicate identities/conflicts, ZIP traversal and expansion restrictions, DuckDB/Parquet provenance |
| Genome | Expiry-effective historical rule selection, purity/quotation/lot distinction, Mumbai/Ahmedabad basis, unknown calendar blocks, tender/expiry boundaries, integer hedge feasibility |
| Financial math | Independent INR examples, long/short lot P&L, all-in fees, dated component fees/GST/taxes, net reconciliation, fine-metal mismatch, empirical curve and roll-down examples, Hypothesis-generated sign symmetry |
| Historical integrity | Shifted reference statistics, post-cutoff price mutation, held-out price mutation with fixed parameters, future-listed contract contamination, no same-session fills, no Open substitution, stable replay prefixes |
| Advanced engines | Reproducible paired bootstrap and correlation behavior, cost/delay sensitivity, prior-only analog scaler and outcome selection, full-policy rejection records |
| Audit | Deliberately wrong fill dates, fractional lots and altered P&L produce failed invariants; untested checks remain not-evaluable |
| Integration | Import→DuckDB→engines→orchestrator→ledger/certificate→FastAPI; snapshot reproduction and tamper detection |
| UI | Six Streamlit AppTest tests exercise all 13 pages, synthetic labeling, exact-expiry/config dispatch, settings persistence, replay stepping, and offline/validation error behavior |

## Actual file coverage

All five named exports were submitted to the running application's import API. It retained their original bytes and hashes, rejected annual aggregates, and recognized the duplicate 2023 file. Rejected rows by file were 36, 35, 35, 33, 41, respectively; 180 total including the duplicate. These are annual report rows, not 180 market sessions. No daily observations or real expiry histories were created. The source profile and exact SHA-256 values are in [data_sources.md](data_sources.md).

The separately generated seed 42 synthetic dataset contains 2,160 records: 180 modeled weekdays from 2025-01-02 through 2025-09-10, four symbols and 12 fictional expiry identities. The GOLDM/GOLDTEN investigation snapshot contains 1,080 records including the two products' three maturities. The Parquet snapshot was read back and its 2,160-row count confirmed.

## End-to-end results

Final seeded investigation: `053f619c-d504-4c7c-8db9-204ddb2519cb`.

Configuration: synthetic mode, GOLDM/GOLDTEN, 2025-01-02 to 2025-09-10, cutoff 2025-09-10, window 20, policy C, costs 5 bps plus 2 bps slippage, seed 42, 500 paths. The complete pipeline ran through the live HTTP API in **11.80 seconds** on this machine. This is a small-dataset performance observation, not a large-history benchmark.

- Mirage produced real calculations from the synthetic snapshot.
- Ghost Market executed 11 scenario classes, with 500 paths per scenario.
- Anomaly DNA retrieved five completed prior analogs.
- The full prospective policy rejected 17 candidate sessions and completed zero trades.
- Red Team recorded 10 passes, 0 failures and 11 not-evaluable checks. Unresolved checks include recorded reuse of the evaluation dataset. Absence of trades leaves trade-specific checks unresolved.
- Verdict: **INSUFFICIENT EVIDENCE**. Execution feasibility: **Unverified**.
- Final-period boundary: 2025-07-21; prior training ended 2025-07-18. The same declared boundary is retained during cutoff stepping.

For demonstration of the actual lot/P&L engine, baselines A and B each completed six **synthetic** trades. Both had₹46,548.671 gross,₹15,234.869 modeled costs and₹31,313.802 net. Their two held-out synthetic trades had₹11,218.268 net. They match because the selected pair shares one expiry and therefore has zero maturity differential. These intentionally generated prices do not establish any historical MCX profitability, statistical significance or real fill feasibility. Full policy C accepted none of those opportunities.

The preserved-snapshot reproduction API returned `match: true` with both result hashes:

```text
b94c797c7526950344b07465b61ca53a7f6fbaff0000164ddab3bba0a246177f
```

Snapshot hash:

```text
28e8639b9546f985b35e274e56ca8b968da1f3ad4be087fd2ef05c41fa4da7d9
```

The final real-mode investigation `fe889f6c-1b64-42ce-982c-d41662ea0fa5` returned **INSUFFICIENT EVIDENCE**, zero observations, zero sessions, and “No meaningful opportunity identified under the selected assumptions.” Earlier development experiments are preserved in the ledger; they are not silently deleted. Older code hashes require their corresponding implementation for reproduction.

## Service and user-interface checks

The live FastAPI health endpoint returned `status: ok`; Streamlit's health endpoint returned `ok`. The dashboard was opened in the connected Chrome browser and visually inspected. Real mode showed zero genuine history. Switching to synthetic mode displayed the explicit warning and correct 2,160-record/12-contract coverage. Clicking Relative Value Explorer's comparison button returned 180 paired sessions, normalized-price chart controls, exportable records, and the no-opportunity conclusion. The plotted normalized series were visually checked. Evidence Center loaded the final certificate; clicking its reproduction button returned `match: true` and identical hashes in the browser. Automated UI tests additionally cover control dispatch and all 13 workspaces. No proprietary interface/logo was copied.

## Status and remaining limitations

All seven named analytical modules have executable functionality and tests. The import pipeline, thirteen-workspace UI, dated cost assumptions, three research policies, ledger, certificates, and reproduction are integrated. The no-LLM path is fully functional.

Real-data execution validity and statistically meaningful historical results remain **blocked by missing data/evidence**, not passed. Direct official PDF retrieval returned 403; original specification-document hashes are therefore null, and real listing/tender calendars remain unverified. All such restrictions block execution claims. Manual daily-file ingestion is implemented and tested using independent fixtures; the supplied files cannot demonstrate authentic daily-history performance.

Optional LLM integration, cointegration/error-correction models, calibrated predictive probabilities, causal alpha attribution, and persistent cancellable jobs are not implemented. Docker/Compose files are supplied but **Docker was not available, so its build and runtime are unverified**. Dependencies passed consistency checks; no external vulnerability-feed audit or third-party security certification was performed. Archive/input/path safeguards were tested locally.

Priority follow-up: obtain genuine daily Bhavcopy history and dated contract calendars; complete source/fee provenance; independently review methodology; expand final-period samples and calibrated uncertainty; add cancellable background jobs for longer histories.
