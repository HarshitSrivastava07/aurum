# Data provenance and ingestion

## The five supplied files

Inspected read-only on 2026-10-09. All five `.xls` files contain HTML tables, not binary Excel workbooks. They report annual commodity trading activity. They do **not** contain a session date, contract expiry, OHLC, settlement price or open interest. These are unsuitable for daily relative-value research or backtesting. The filename's `2026-10-9` is not an observation date.

| File suffix | Report year | Rows | SHA-256 |
|---|---:|---:|---|
| `Detail report.xls` | 2025 | 41 | `33489b17fadacd05a15ff1f9b8d2d0dc003bd83b97a76d21ac4997c931658e84` |
| `Detail report (1).xls` | 2024 | 36 | `660e58f1462ca994eaa6c1bcc8bb75584e98ef2b1a04ad374c1ba894f406f584` |
| `Detail report (2).xls` | 2023 | 35 | `42c71560987d2a4de3a6c85f5a8f160fa8105c66298d56a6b8d36e83bdaabd1a` |
| `Detail report (3).xls` | 2023 | 35 | `42c71560987d2a4de3a6c85f5a8f160fa8105c66298d56a6b8d36e83bdaabd1a` |
| `Detail report (4).xls` | 2021 | 33 | `bf491715a236b6a9bf2256f542d01d457dbbd229bbcf3e855d3f6831c02ab200` |

Files (2) and (3) are byte-identical. No report for 2022 was supplied. Every table has `Instrument`, `Year`, `Segment`, `Commodity`, `Traded Contract (Lots)`, `Total Value (Lakhs)`, `Avg Daily Turnover(Lakhs)`, and `Premium Value (Lakhs)`. The 2025 table includes GOLDTEN; the older tables do not. A yearly average turnover is not a daily contract price. The importer preserves raw bytes and a rejection report rather than generating observations from these aggregates.

## Official acquisition

- [MCX Bhavcopy](https://www.mcxindia.com/market-data/bhavcopy) is the requested official entry point. The Gold product page links to `/market-data/bhav-copy`; both were checked. The browsing fetch failed because the returned content exceeded the tool's 4 MiB limit. This does not establish that the exchange site is unavailable to users.
- [MCX Gold products](https://www.mcxindia.com/products/bullion/gold) was accessible and its official PDF links were followed and inspected. Direct programmatic requests for all twelve selected PDFs returned **HTTP 403**. No protection bypass was attempted. No guessed API endpoint or endpoint inferred from third-party libraries is implemented.
- Manual import is therefore the functioning acquisition route. Download a daily contract-wise Bhavcopy export from MCX in the user's browser and upload the original CSV/XLS/XLSX/ZIP. The application does not assert that an arbitrary uploaded file is exchange-authenticated merely because its schema matches.
- `data/specifications/fetch_sources.py` is an explicit-URL, bounded manual acquisition helper for the reviewed PDFs. It records success/failure and hashes actual returned PDF bytes only. `source_audit.json` retains the observed failures. No automatic retry loop runs at application startup.

## Canonical daily schema

Each row preserves `symbol`, `instrument`, `date`, `expiry`, `open`, `high`, `low`, `close`, `previous_close`, `settlement`, `volume`, `open_interest`, `trading_value`, `source_file`, `requested_date`, `returned_date`, `import_timestamp`, `source_hash`, `validation_status`, `mode`. Dates use ISO `YYYY-MM-DD`; import timestamp uses UTC. Keys are `(mode,symbol,instrument,date,expiry)` so changing expiries are never stitched into one return series.

| Canonical | Accepted examples |
|---|---|
| symbol | Commodity, Symbol, TckrSymb |
| instrument | Instrument, InstrumentType, FinInstrmTp |
| date | Date, TradingDate, TradeDate, TradDt, BizDt |
| expiry | Expiry, ExpiryDate, Expiry Date, XpryDt, FinInstrmActlXpryDt |
| OHLC | Open/High/Low/Close, OpenPrice/HighPrice/LowPrice/ClosePrice, OpnPric/HghPric/LwPric/ClsPric |
| previous_close | Previous Close, PrevClose, PrvsClsgPric |
| settlement | Settlement, Settlement Price, SettlePrice, SttlmPric |
| volume | Volume, Vol, Vol (Lots), Volume (Lots), TtlTradgVol |
| open_interest | OI, OI (Lots), Open Interest, OpenInterest (Lots), OpnIntrst |
| trading_value | Trading Value, Value, Turnover, TtlTrfVal, TtlTrdVal |

Header matching ignores spaces, punctuation and case. Only the four supported gold futures symbols are admitted; options and other commodities are counted as skipped. Missing Instrument is explicitly treated as FUTCOM for otherwise valid gold daily exports. Unit labels outside this adapter require a reviewed mapping; no Lakhs-to-INR conversion is silently inferred.

The import setting declares whether numeric returned dates are MDY or DMY. Default MDY handles exchange exports such as `04/09/2026` as 9 April. Requested dates use DMY, so `09/10/2026` requests 9 October. ISO dates and `04SEP2026` are unambiguous. An invalid date never triggers a fallback to the other order. Requested/returned mismatch is retained as a warning; the actual returned date remains the observation date. Future requests, future observations, impossible dates and observations after expiry are rejected. An expiry itself may lie in the future.

Close and settlement remain separate. Missing settlement stays null. Missing Open blocks an Open-based execution proxy in downstream checks. Missing liquidity is a warning, not an imputed zero. Nonfinite or nonpositive prices, negative volume/OI, fractional lots and inconsistent OHLC are rejected. Conflicting duplicate rows are quarantined; existing accepted prices are never silently overwritten. Exact duplicate records are counted and skipped. Raw hash duplication is tracked independently, including rejected annual files.

## Storage and safety

Original content is saved under SHA-256-prefixed, sanitized filenames in the storage directory's `raw/`. Rejected bounded files are retained for audit. DuckDB is the source of truth. A mode-specific Parquet snapshot is updated after successful inserts. Snapshot failure is surfaced in the import report while accepted DuckDB data remains available. Synthetic and real rows are partitioned by mode in every query and snapshot; selecting all modes is unsupported.

Supported input readers are CSV, TSV, binary XLS (xlrd), XLSX (openpyxl), and HTML tables including `.xls` HTML exports. The parser does not execute workbook macros, formulas, HTML instructions or scripts. XLSX reads cached values only and disables external links. Imports are limited to 25 MiB per file and 250,000 rows. ZIP imports read members in memory, allow at most 50 files/100 MiB expanded, and reject traversal paths, symlinks, encrypted members, nested archives, unknown member types and excessive compression ratios. No archive member is extracted to an attacker-controlled path.

Missing observations are never forward-filled. Contract coverage can compare against dates actually observed elsewhere in the selected dataset. A missing row does not prove a holiday, suspended contract, untraded contract or missing download. Calendar and completeness uncertainty remains explicit.

## Contract Genome evidence and limits

`registry.json` preserves twelve official PDF versions plus four unverified challenge baselines. `effective_from` and `effective_to` describe the **expiry contract month** covered by a PDF, not the observation date. Concurrent contracts can use different specification versions. The selector requires the actual expiry to select a reviewed version. Earlier uncovered periods retain only the unverified baseline. GOLDTEN is unavailable before its 2025 introduction in the baseline selector.

The official PDFs establish separate lot and quotation sizes: GOLDM 100g/10g, GOLDTEN 10g/10g, GOLDGUINEA 8g/8g, GOLDPETAL 1g/1g. GOLDM uses .995 reference purity; the others .999. Price normalization is `raw / quotation_grams`, then `/ purity`, yielding INR per fine gram. This is a linear metal-content adjustment. It does not resolve taxes, delivery premia or geographical basis. [GOLDPETAL July 2026 specification](https://www.mcxindia.com/docs/default-source/about-us/gold-petal-july-2026-contract-onwards.pdf) quotes Ex-Mumbai; [GOLDTEN July 2026 specification](https://www.mcxindia.com/docs/default-source/about-us/gold-ten-july-2026-contract-onwards.pdf) quotes Ex-Ahmedabad. The location difference remains an unresolved basis risk.

Historical rules materially differ. [GOLDTEN April 2025 specification](https://www.mcxindia.com/docs/default-source/products/contract-specification/gold-ten/gold-ten-april-2025-contract-onwards7fb63e4857fb64e3bdfdff00007acb3580008247-f6c1-4a56-be21-ac18ff0bdbe4.pdf) uses five tender trading days; [GOLDTEN November 2025 specification](https://www.mcxindia.com/docs/default-source/products/contract-specification/gold-ten/gold-ten-november-2025-contract-onwards9a08564857fb64e3bdfdff00007acb35.pdf) uses three. Guinea January 2025 and Petal April 2025 similarly use five, changing to three in their December 2025 versions. Source URLs for every record are stored in the registry.

The PDFs were inspected via browsing, but raw download failures mean `source_hash` is null. `fields_reviewed=true` identifies extracted fields; `verified=false` means full provenance, historical rule coverage and execution calendars remain incomplete. Publication availability at a historical signal cutoff is not inferred from today's PDF. Fees are null. Reviewed rules do not by themselves verify a contract's actual listing date, tender start, special sessions or holiday adjustments. Real execution remains blocked until this evidence is supplied. `lifecycle()` never substitutes weekdays for exchange trading days.

`synthetic.json` is a separate four-contract fixture registry with `mode=synthetic` and explicit fictional provenance. Its three-day tender period uses modeled calendar days, including expiry, solely for deterministic demonstrations/tests. Fixture validation does not verify an MCX contract. Position sizing uses positive integer lots and fully funded combined gross notional, reports residual fine-gold exposure, and does not assume broker margin or leverage.
