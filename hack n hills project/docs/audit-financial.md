# Financial implementation and evidence audit

Audit work: 24–26 October 2026. Official specification pages were inspected on 24 October. This report covers financial engines, source provenance and their tests; the application-wide UI/API report covers the remaining workflows.

The application calculates real outputs from its selected inputs. That does **not** establish authentic MCX history, executable fills, or a profitable strategy. No authenticated daily MCX sample was acquired during this audit. Imported files therefore remain **IMPORTED UNVERIFIED DATA**; deterministic examples remain **SYNTHETIC TEST DATA**. **REAL MCX DATA** is reserved for independently authenticated evidence, for which the application currently has no completed verification path.

## Implemented modules and limits

The classifications describe the stated research functionality, not exchange certification or predictive validity.

| Module | Classification | Inspected implementation and evidence | Remaining qualification/action |
|---|---|---|---|
| `backend/services/genome.py` and `data/specifications/` | PARTIALLY IMPLEMENTED | Expiry-month specification selection; quotation/lot/purity normalization; integer hedge sizing; listing/tender/expiry gates. `test_genome.py` and known-answer financial tests exercise boundaries and monetary units. | All 16 real registry entries remain unverified. Original PDF hashes, publication availability and exact listing/tender calendars are absent. Do not promote these entries merely because fields match current PDFs. |
| `backend/services/analytics.py` | FULLY IMPLEMENTED for descriptive relative value | Exact-expiry joins; pre-cutoff filtering; shifted mean/std/MAD references; liquidity flags; bracketing empirical curve interpolation without extrapolation. Tests check independent units/statistics, missing sessions and future mutations. | Empirical curve adjustment does not value financing, storage, tax or delivery optionality. Automatic discovery selection is retrospective within its declared cutoff; replay freezes identities separately. |
| `backend/services/analogs.py` | FULLY IMPLEMENTED for descriptive analog retrieval | Fixed interpretable features, robust scaling fitted to prior completed candidates, nonoverlapping outcome horizons and outcomes strictly before the query date. `test_analogs.py` tests these restrictions. | Similarity and narrowing frequency are not calibrated profit forecasts or costed executable returns. |
| `backend/services/replay.py` | PARTIALLY IMPLEMENTED | Chronological signals, later common-session Open proxies, integer positions, exact expiry identity, dated fees, open-position marks, fixed holdout boundary, replay events and per-session drawdown. Independent money/accounting and mutation tests exercise actual filled fixtures. | Real two-leg execution, broker margins, intraday depth, official trading calendars and actual settlement/delivery processes are unverified. Capital is a fully funded gross-notional cap, not a margin model. |
| `backend/services/costs.py` | FULLY IMPLEMENTED for explicit assumptions | Date-effective fee components, signed buy/sell taxes, brokerage, exchange/regulatory fees, GST and slippage; uncovered dates reject actual modeled fills. Independent numerical tests reconstruct fees. | No verified historical exchange/broker tax schedule is supplied. User-entered assumptions are not certified fee history. |
| `backend/services/scenarios.py` | FULLY IMPLEMENTED for declared counterfactual diagnostics | Joint circular-block sampling; 12 explicit stress classes; cost/delay replay grid and six independent sensitivity slices. Seed, correlation, cost and failed-leg known-answer tests execute these computations. | Sampled paths, tail estimates and positive frequencies are not calibrated probabilities. Cost schedules are frozen to an effective cutoff turnover rate in simulated scenarios. |
| `backend/services/red_team.py` | FULLY IMPLEMENTED for its 21 declared invariants | Executable source-date, mode, unit, expiry, future-mutation, lagged-fill, integer, lifecycle, cost, attribution, sample and other checks. Signal-volume trade sizing now independently rejoins source observations. Adversarial mutations demonstrate failures. | Unit identities cannot authenticate a bad source specification by themselves. Missing evidence remains not-evaluable. Daily volume cannot establish order-book depth. |
| `backend/services/ingestion.py` | PARTIALLY IMPLEMENTED end-to-end acquisition | CSV/XLS/XLSX/HTML/ZIP normalization, strict dates, independent expiry identity, bounded inputs, duplicate/conflict handling, separate Close/settlement, and retained hashes/timestamps are tested. | Authentic official daily-file acquisition and exchange publication timestamps remain unverified; no automatic protected-site bypass or fabricated data is supplied. |
| `backend/services/storage.py` | FULLY IMPLEMENTED for local persistence | DuckDB identity keys, raw files, Parquet snapshots, conflict rejection, imports and coverage. Provenance metadata now accompanies summaries, reports and contracts, including historical reports when read. | Schema validity and SHA-256 identify preserved bytes, not their truth or exchange origin. No authenticity flag can be supplied by an uploaded file. |
| `backend/services/demo.py` | FULLY IMPLEMENTED | Seeded fictional prices and planted conditions, isolated synthetic storage, explicit model calendar. | Identical model coverage is intentional and must never be described as actual listing history. |
| `backend/services/ledger.py` and `orchestration.py` | FULLY IMPLEMENTED for local evidence workflow | Configuration/specification/data/code/result hashes, staged calculations, ledger, export and reproduction refusal on changed inputs/code. Existing API and verdict tests exercise these paths. A certificate provenance gate prevents unverified real-source certification. | Local hashes are not externally anchored signatures. Repeated holdout use is not fresh validation; reproduction of older evidence requires its recorded engine code. |
| `backend/services/education.py` | FULLY IMPLEMENTED | Backend-only hypothetical quotation comparison calls canonical Genome normalization. Input and exact known-answer tests execute it. | Its 995/999 characteristics are declared educational assumptions, not date-effective specifications or imported prices. |
| LLM/cointegration/error-correction/calibrated predictive probability model | NOT IMPLEMENTED | No such calculation is used by the audited financial pipeline. | Do not imply these capabilities or turn descriptive outputs into forecasts. |

## Verified corrections and extensions

1. **Benchmark fees omitted dated schedules.** Actual strategy fills used `fill_cost`, but directional/fixed-pair descriptive benchmarks used aggregate basis points even when a component schedule was selected. An independent fixture with ₹11 entry and ₹29 exit brokerage per lot reproduced a ₹400 overstatement for a ten-lot benchmark. Both benchmarks now use the applicable entry/mark-date schedule. If a schedule does not cover an optional benchmark's dates, that benchmark is unavailable with no invented net value; actual strategy-fill fee coverage remains strict. Their final Close remains a descriptive mark, not a verified liquidation.
2. **The liquidity audit did not test its claimed sizing rule.** It inspected candidate flags but did not reconcile trade quantities to signal-time source volume. Reducing the source signal volume to ten lots left its status incorrectly passing. It now rejoins each trade's exact signal date/product/expiry, checks volume/OI and compares quantities to participation and maximum-lot limits. No future-session volume is used to size or validate that historical decision.
3. **A failed hedge was absent from scenario coverage.** The new explicit scenario assumes leg A fills and leg B never fills. A is unwound after one modeled session, with the adverse common-factor overlay and five times configured slippage. Only the filled leg incurs P&L/turnover costs; signed unhedged fine-gram exposure is returned. This twelfth required class participates in the existing complete-stress and positive-median gates. It does not estimate a hedge-failure probability.
4. **Capital/position-size sensitivity was missing.** The survival report adds half-capital and halved maximum-lot slices. Each reruns chronological replay and integer sizing; the smaller-capital fixture correctly produces no trades when one lot of each leg cannot be funded. The existing cost grid remains separate from dated-schedule slices.
5. **Oversized bootstrap blocks allocated unnecessary memory.** The implementation previously allocated indexes for an entire requested historical block before truncating to the modeled horizon. Capping a block at that horizon preserves the seeded truncated paths and prevents this excess allocation. Flat paired returns now report correlation as null without a NumPy divide-by-zero warning.
6. **Drawdown charts needed actual backend series.** Equity records now expose nonnegative `drawdown_fraction` directly from the existing cumulative-peak drawdown calculation. Independent peak arithmetic checks every point; its maximum equals the existing `max_drawdown` metric. No chart-side financial calculation is required.
7. **Data mode was insufficient provenance.** Summary/import/contract outputs now distinguish SYNTHETIC TEST DATA from IMPORTED UNVERIFIED DATA and carry `source_authenticity_verified: false`. Import reports retain source identifiers (`sha256:...`), timestamp, actual newly inserted coverage and contract identities. `has_imported_history` distinguishes uploaded rows from authenticated real history; `has_real_history` remains false. The certificate-level positive-verdict provenance gate is implemented in the API/orchestration workstream.

These changes alter diagnostic outputs and engine code hashes. Existing evidence files are preserved; a previous certificate must be reproduced with its recorded implementation, not silently compared against the revised engine.

## Independent numerical answers

- GOLDM, one 100g lot, quote per 10g, ₹100,000 entry to ₹105,000 exit: `(105000 - 100000) × 100 / 10 = ₹50,000` gross. One short lot gives −₹50,000. The same quoted change for one assumed 10g GOLDTEN lot gives ₹5,000.
- Under the explicitly hypothetical proportional fine-metal assumption, a ₹100,000 quote at 995 fineness becomes `100000 × 999 / 995 = ₹100,402.01005025125` per 10g at 999 fineness.
- Against ₹101,000 for the illustrative GOLDTEN quote, the comparable difference is `₹597.9899497487437` per 10g. The raw ₹1,000 difference is not the adjusted difference. Neither number is an arbitrage certification.
- The failed-hedge test uses flat independent synthetic quotes and reconstructs the declared adverse path, one-leg multiplier and turnover fees by hand. It verifies that the failed leg contributes neither P&L nor fill charges.

## Official source evidence

The official [MCX Gold products page](https://www.mcxindia.com/products/bullion/gold) and linked specifications were browsable on 24 October 2026. Current listed versions support these fields; their applicability is to the specified **expiry contract months**, not every historical observation.

| Product | Trading unit / quotation unit | Reference fineness | Primary quotation/delivery location | Official current listed version |
|---|---|---|---|---|
| GOLDM | 100g / 10g | 995 | Ahmedabad | [August 2026 onwards](https://www.mcxindia.com/docs/default-source/about-us/gold-mini-august-2026-contract-onwards8a79913a-e8de-4136-9f0b-25d31dc163c4.pdf) |
| GOLDTEN | 10g / 10g | 999 | Ahmedabad | [July 2026 onwards](https://www.mcxindia.com/docs/default-source/about-us/gold-ten-july-2026-contract-onwards.pdf) |
| GOLDGUINEA | 8g / 8g | 999 | Ahmedabad | [July 2026 onwards](https://www.mcxindia.com/docs/default-source/about-us/gold-guinea-july-2026-contract-onwards.pdf) |
| GOLDPETAL | 1g / 1g | 999 | Mumbai | [July 2026 onwards](https://www.mcxindia.com/docs/default-source/about-us/gold-petal-july-2026-contract-onwards.pdf) |

Units/ticks appear on page 1; purity, locations and tender rules principally on pages 1–2. These current versions specify the last three trading days including expiry for tender. GOLDM expires on the fifth, adjusted to the preceding working day when required; the others use month-end with working-day adjustment. Actual dates still require the exchange calendar. Delivery/settlement provisions and locations differ, so these products are not economically interchangeable. The current GOLDM PDF cites MCX/TRD/041/2026 (27 January), MCX/PMT/178/2026 (6 April) and MCX/PMT/375/2026 (1 July); expiry-version labels are not publication timestamps.

All eight earlier reviewed versions were also accessible and match stored registry transitions:

| Product | Earlier official versions | Tender trading days |
|---|---|---|
| GOLDM | [November 2025](https://www.mcxindia.com/docs/default-source/products/contract-specification/gold-mini/gold-mini-november-2025-contract-onwardsfc22554857fb64e3bdfdff00007acb35.pdf); [May 2026](https://www.mcxindia.com/docs/default-source/about-us/gold-mini-may-2026-contract-onwards.pdf) | 3; 3 |
| GOLDTEN | [April 2025](https://www.mcxindia.com/docs/default-source/products/contract-specification/gold-ten/gold-ten-april-2025-contract-onwards7fb63e4857fb64e3bdfdff00007acb3580008247-f6c1-4a56-be21-ac18ff0bdbe4.pdf); [November 2025](https://www.mcxindia.com/docs/default-source/products/contract-specification/gold-ten/gold-ten-november-2025-contract-onwards9a08564857fb64e3bdfdff00007acb35.pdf) | 5; 3 |
| GOLDGUINEA | [January 2025](https://www.mcxindia.com/docs/default-source/products/contract-specification/gold-guinea/gold-guinea-january-2025-contract-onwards8992f3f6-d244-425a-9a53-66d94500bb34.pdf); [December 2025](https://www.mcxindia.com/docs/default-source/products/contract-specification/gold-guinea/gold-guinea-december-2025-contract-onwardsdc22554857fb64e3bdfdff00007acb35.pdf) | 5; 3 |
| GOLDPETAL | [April 2025](https://www.mcxindia.com/docs/default-source/products/contract-specification/gold-petal/gold-petal-april-2025-contracts-onwards4b958087-3b38-44b0-abc2-30acd903c1ad.pdf); [December 2025](https://www.mcxindia.com/docs/default-source/products/contract-specification/gold-petal/gold-petal-december-2025-contracts-onwards7a08564857fb64e3bdfdff00007acb35.pdf) | 5; 3 |

No discrepancy was found in those stored units, purity, locations, tender transitions or expiry-month version bounds. This field-level review does not fill the missing raw PDF hashes, historical publication timestamps, listing/tender dates or earlier historical rule coverage. `select_spec()` does not enforce `known_at`; any future promotion to verified specifications must add publication-availability checks. All real entries currently remain unverified, so their lifecycle gates block execution claims. In particular, GOLDTEN's baseline start at its March 2025 circular date must not be treated as its actual contract listing date.

The official [Bhavcopy page](https://www.mcxindia.com/market-data/bhavcopy?slinkpage=y) exceeded the browsing tool's 4 MiB content limit. Its indexed headers and the [MCX datafeed description](https://classic.mcxindia.com/technology/datafeed) identify contract-wise end-of-day OHLC, volume, value and OI, but no dated daily file or authenticated market row was obtained. Existing raw-PDF HTTP 403 failures are retained in `data/specifications/source_audit.json` and documented in `data_sources.md`; this audit did not re-run those raw downloads or infer that the exchange site is unavailable to users. No guessed endpoint or third-party market sample substitutes for official evidence.

## Existing dataset inspection

A read-only DuckDB query during the 24 October work found only the synthetic partition: 2,160 rows, one source hash, 2 January through 10 September 2025. There were twelve product/expiry identities, each with exactly 180 sessions, and zero real-mode rows. The registry contained sixteen real entries, none verified.

`demo.py` explicitly loops over four symbols, three fictional expiries and the same 180 modeled business weekdays. This explains identical coverage. The output is labeled synthetic, and those weekdays are not an MCX holiday/listing calendar. No missing history was reconstructed as real data. The earlier supplied annual activity files and their hashes are documented in `data_sources.md`; those historical file-inspection results were not newly re-executed in this financial workstream.

## Executed validation

- Before the fee/liquidity corrections, `python -m pytest tests/test_master_financial.py -q` completed with **8 passed, 2 failed in 10.03s**. The failures were the independent dated-benchmark-fee and signal-volume mutation assertions described above.
- After those corrections and the new scenario/sensitivity/provenance tests, the focused command below completed with **36 passed in 31.81s**. It reported two undefined-correlation warnings on deliberately flat returns; the subsequent zero-variance guard addresses that case. This result precedes the final drawdown and fee-coverage follow-up checks.

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_master_financial.py tests/test_scenarios.py tests/test_costs.py tests/test_replay.py tests/test_verdict_integrity.py -q
```

On 26 October, a follow-up regression first reproduced an uncovered benchmark-fee-date exception on an otherwise valid no-trade run (**1 failed in 39.42s**). The optional benchmark now reports unavailable while the no-trade replay remains inspectable. Actual trade fee requirements were not relaxed.

Final focused execution on 26 October completed with **38 passed, 0 failed, no warnings in 81.08s**:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_master_financial.py tests/test_scenarios.py tests/test_costs.py tests/test_replay.py tests/test_verdict_integrity.py -q --junitxml=logs/financial-audit-2026-10-26.xml
```

Machine-readable evidence is retained in `logs/financial-audit-2026-10-26.xml`. This final run includes all prior focused cases, the backend drawdown/zero-variance correlation checks and uncovered benchmark-fee handling. No result from an interrupted or uncollected test process is counted as a pass. The root application audit records its separate full-suite and UI results.

## Remaining financial evidence requirements

- Obtain and preserve authentic dated daily Bhavcopy files, with requested/returned-date checks, and independently authenticate their source. A plausible CSV schema is insufficient.
- Preserve original date-effective specification bytes/hashes and publication availability; obtain official listing dates, tender boundaries, expiry adjustments and historical fee rules. Earlier data must not inherit today's rules.
- Treat OHLC/Open proxies, volume-based participation, fully funded gross notional and bootstrap overlays as explicit models. No daily file can establish simultaneous executable depth, actual brokerage margins or fill certainty.
- Keep insufficient samples, unresolved lifecycle checks, unclosed positions and unauthenticated source conclusions unresolved. A passing software test or a positive synthetic P&L is not evidence of an MCX trading edge.
