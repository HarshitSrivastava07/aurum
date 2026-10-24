"""Reproduce the audited registry from explicit sources and field review notes.

This script does not promote a reviewed PDF to fully verified execution metadata.
Archive hashes, contemporaneous publication proof and expiry calendars are absent.
"""
import json
from pathlib import Path
from fetch_sources import BASE, SOURCES

ROOT = Path(__file__).resolve().parent
PRODUCTS = {"GOLDM": (100, 10, .995, "Ahmedabad"), "GOLDTEN": (10, 10, .999, "Ahmedabad"),
            "GOLDGUINEA": (8, 8, .999, "Ahmedabad"), "GOLDPETAL": (1, 1, .999, "Mumbai")}
records, synthetic = [], []
for symbol, (unit, quote, purity, location) in PRODUCTS.items():
    common = {"symbol": symbol, "exchange": "MCX", "underlying": "Gold", "trading_unit_g": unit,
              "quotation_unit_g": quote, "purity": purity, "tick_size": 1.0, "quote_location": location,
              "delivery_location": location, "additional_delivery_locations": [x for x in ("Ahmedabad", "Mumbai", "New Delhi") if x != location],
              "expiry_rule": "5th of expiry month or preceding exchange trading day" if symbol == "GOLDM" else "Last calendar day of expiry month or preceding exchange trading day",
              "fees": None, "last_trading_date": "Use the actual expiry in the observation and official calendar",
              "delivery_provision": "Compulsory delivery", "effective_basis": "expiry_contract_month",
              "known_at": None, "reviewed_on": "2026-10-09", "mode": "real"}
    records.append({**common, "spec_id": f"{symbol}-challenge-baseline-unverified", "baseline": True,
                    "effective_from": "2025-03-18" if symbol == "GOLDTEN" else "1900-01-01", "effective_to": None,
                    "verified": False, "fields_reviewed": False, "verification_status": "challenge_baseline_only",
                    "tender_days": None, "tender_day_basis": None, "source_url": "https://www.mcxindia.com/products/bullion/gold",
                    "source_hash": None, "limitations": ["Challenge baseline; not date-effective official contract rules", "Unknown tender boundary blocks modeled execution"]})
    for product, start, end, suffix in SOURCES:
        if product != symbol:
            continue
        tender_days = 5 if (symbol == "GOLDTEN" and start == "2025-04-01") or (symbol == "GOLDGUINEA" and start == "2025-01-01") or (symbol == "GOLDPETAL" and start == "2025-04-01") else 3
        records.append({**common, "spec_id": f"{symbol}-expiry-{start}", "baseline": False,
                        "effective_from": start, "effective_to": end,
                        "verified": False, "fields_reviewed": True,
                        "verification_status": "official_pdf_reviewed_archive_and_calendar_unverified",
                        "tender_days": tender_days, "tender_day_basis": "exchange_trading_days_including_expiry_excluding_special_sessions",
                        "source_url": BASE + suffix, "source_document_url": BASE + suffix, "source_hash": None,
                        "field_evidence": {"units_quote_tick": "PDF page 1", "purity": "PDF pages 1-2", "tender": "Staggered Delivery Tender Period section"},
                        "limitations": ["Official PDF inspected through browsing; raw download returned HTTP 403, so original PDF hash unavailable", "Full historical rule coverage and contemporaneous publication availability unverified", "Expiry-specific listing dates and trading/tender calendar must be verified separately", "No adjustment for geographical basis, taxes or delivery premium is inferred"]})
    synthetic.append({**common, "mode": "synthetic", "spec_id": f"SYNTHETIC-{symbol}-v1", "baseline": True,
                      "effective_from": "2020-01-01", "effective_to": None, "verified": True,
                      "verification_status": "synthetic_fixture_only", "fields_reviewed": False,
                      "known_at": "2020-01-01", "tender_days": 3, "tender_day_basis": "modeled_calendar_days_including_expiry",
                      "source_url": None, "source_hash": None, "limitations": ["Fictional test contract; not an exchange-verified specification", "Synthetic tender begins two calendar days before modeled expiry"]})

(ROOT / "registry.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
(ROOT / "synthetic.json").write_text(json.dumps(synthetic, indent=2), encoding="utf-8")
print(f"Wrote {len(records)} real-context records and {len(synthetic)} separate synthetic fixtures")
