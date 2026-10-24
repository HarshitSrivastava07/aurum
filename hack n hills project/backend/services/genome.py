"""Contract Genome: date-effective specifications, normalized metal, lifecycle gates."""
from __future__ import annotations

from copy import deepcopy
from datetime import date as Date, timedelta
import json
import math
from pathlib import Path
from functools import lru_cache

SPEC_DIR = Path(__file__).resolve().parents[2] / "data" / "specifications"
SYMBOLS = ("GOLDM", "GOLDTEN", "GOLDGUINEA", "GOLDPETAL")


@lru_cache(maxsize=16)
def _registry_content(path, modified, size):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def list_specs(mode="real") -> list[dict]:
    if mode not in {"real", "synthetic"}:
        raise ValueError("mode must be real or synthetic")
    path = SPEC_DIR / ("synthetic.json" if mode == "synthetic" else "registry.json")
    if not path.exists():
        return []
    stat=path.stat()
    return deepcopy(_registry_content(str(path),stat.st_mtime_ns,stat.st_size))


def select_spec(specs: list[dict], symbol, date, expiry=None) -> dict | None:
    """Version boundaries refer to expiry-contract months, not observation dates.

    Without expiry we provide only a clearly unverified baseline, since a date can
    have several simultaneously traded contracts governed by different versions.
    """
    symbol = str(symbol).strip().upper()
    Date.fromisoformat(str(date)[:10])
    key = str(expiry)[:10] if expiry else None
    if key:
        Date.fromisoformat(key)
    candidates = []
    for spec in specs:
        if spec["symbol"] != symbol:
            continue
        if spec.get("baseline") and spec.get("effective_from", "0001-01-01") <= str(date)[:10]:
            candidates.append(spec)
        elif key and spec["effective_from"] <= key and (not spec.get("effective_to") or key <= spec["effective_to"]):
            candidates.append(spec)
    if not candidates:
        return None
    chosen = sorted(candidates, key=lambda s: (not s.get("baseline", False), s.get("effective_from") or ""))[-1]
    return deepcopy(chosen)


def get_spec(symbol, date, expiry=None, mode="real") -> dict | None:
    return select_spec(list_specs(mode), symbol, date, expiry)


def _units(spec):
    if not spec:
        raise ValueError("A contract specification is required")
    unit, quote, purity = (float(spec[k]) for k in ("trading_unit_g", "quotation_unit_g", "purity"))
    # Accept both 995 fineness and 0.995 fraction while storing the registry as fractions.
    purity = purity / 1000 if purity > 1 else purity
    if not all(math.isfinite(x) and x > 0 for x in (unit, quote, purity)) or purity > 1:
        raise ValueError("Invalid specification units or purity")
    return unit, quote, purity


def normalize(price, spec) -> dict:
    raw = float(price)
    if not math.isfinite(raw) or raw <= 0:
        raise ValueError("Price must be finite and positive")
    unit, quote, purity = _units(spec)
    return {"raw": raw, "quotation_normalized": raw / quote, "purity_adjusted": raw / (quote * purity),
            "unit": "INR per fine gram", "lot_value": raw * unit / quote,
            "fine_grams_per_lot": unit * purity,
            "assumption": "Linear metal-content normalization; taxes, location and delivery premia remain unresolved.",
            "verified": bool(spec.get("verified")), "spec_id": spec.get("spec_id")}


def lifecycle(row, spec=None) -> dict:
    reasons = []
    mode = str(row.get("mode", "real"))
    result = {"entry_eligible": False, "exit_eligible": False, "execution_status": "blocked", "reasons": reasons,
              "tender_start": None, "days_to_expiry": None, "mode": mode}
    try:
        session = Date.fromisoformat(str(row.get("date"))[:10])
        expiry = Date.fromisoformat(str(row.get("expiry"))[:10])
    except (ValueError, TypeError):
        reasons.append("Missing or invalid observation/expiry date")
        return result
    result["days_to_expiry"] = (expiry - session).days
    spec = spec or get_spec(row.get("symbol"), session.isoformat(), expiry.isoformat(), mode=mode)
    if not spec or not spec.get("verified"):
        reasons.append("No verified specification for this expiry contract")
    if spec and spec.get("mode", "real") != mode:
        reasons.append("Specification and observation modes do not match")
    if session > expiry:
        reasons.append("Observation is after contract expiry")
    if str(row.get("validation_status", "valid")) not in {"valid", "warning"}:
        reasons.append("Observation has not passed data validation")
    if spec and spec.get("tender_days") is None:
        reasons.append("Tender rule is unknown")
    tender = None
    if mode == "synthetic" and spec and spec.get("mode") == "synthetic":
        # This is explicitly a model calendar, never presented as an MCX calendar.
        tender = expiry - timedelta(days=max(int(spec.get("tender_days") or 3) - 1, 0))
    else:
        if row.get("calendar_verified") is not True:
            reasons.append("Expiry-specific trading calendar and tender boundary are not verified")
        if row.get("tender_start"):
            try:
                tender = Date.fromisoformat(str(row["tender_start"])[:10])
            except ValueError:
                reasons.append("Invalid tender boundary")
        if tender is None:
            reasons.append("Actual tender start date is unavailable; trading days are not calendar days")
        if not row.get("listing_date"):
            reasons.append("Official listing date is unavailable")
    if row.get("listing_date"):
        try:
            if session < Date.fromisoformat(str(row["listing_date"])[:10]):
                reasons.append("Session precedes official listing date")
        except ValueError:
            reasons.append("Invalid listing date")
    if tender:
        result["tender_start"] = tender.isoformat()
        if tender > expiry:
            reasons.append("Tender boundary is after expiry")
        if session >= tender:
            reasons.append("Session is in tender/delivery period; no modeled trading permitted")
    result["entry_eligible"] = not reasons
    result["exit_eligible"] = not reasons
    result["execution_status"] = ("hypothetical_synthetic" if mode == "synthetic" else "eligible_hypothetical_proxy") if not reasons else "blocked"
    return result


def integer_hedge(spec_a, spec_b, price_a, price_b, capital, max_lots=100) -> dict:
    """Minimize residual fine-metal fraction, then favor lower gross notional.

    Both lots must be positive, each bounded by max_lots. Capital caps combined
    gross notional (no assumed leverage/margin). Never claim exact neutrality
    unless the resulting fine-metal residual is actually zero.
    """
    unit_a, quote_a, purity_a = _units(spec_a)
    unit_b, quote_b, purity_b = _units(spec_b)
    capital, price_a, price_b = map(float, (capital, price_a, price_b))
    if not all(math.isfinite(x) and x > 0 for x in (capital, price_a, price_b)):
        raise ValueError("Capital and prices must be finite and positive")
    if not isinstance(max_lots, int) or not 1 <= max_lots <= 1000:
        raise ValueError("max_lots must be an integer in [1, 1000]")
    va, vb, fa, fb = price_a * unit_a / quote_a, price_b * unit_b / quote_b, unit_a * purity_a, unit_b * purity_b
    best = None
    for a in range(1, min(max_lots, int(capital // va)) + 1):
        upper = min(max_lots, int((capital - a * va) // vb))
        if upper < 1:
            continue
        # For fixed a, absolute residual / total fine grams decreases up to
        # b=a*fa/fb and increases thereafter. Only adjacent feasible integers
        # can minimize it; this is exact, without a quadratic lot search.
        target = a * fa / fb
        choices = {max(1, min(upper, math.floor(target))), max(1, min(upper, math.ceil(target)))}
        for b in choices:
            gross = a * va + b * vb
            residual = a * fa - b * fb
            score = (round(abs(residual) / (a * fa + b * fb), 14), gross)
            if best is None or score < best[0]:
                best = (score, a, b, residual, gross)
    if best is None:
        return {"lots_a": 0, "lots_b": 0, "fine_grams_residual": None, "residual_fine_g": None,
                "notional": 0.0, "gross_notional": 0.0, "eligible": False, "reason": "Capital cannot fund one lot of each leg"}
    _, a, b, residual, gross = best
    return {"lots_a": a, "lots_b": b, "fine_grams_residual": residual, "residual_fine_g": residual,
            "notional": gross, "gross_notional": gross, "eligible": True,
            "residual_fraction": abs(residual) / (a * fa + b * fb), "exact_metal_neutral": abs(residual) < 1e-9,
            "capital_assumption": "Combined gross notional fully funded; no leverage", "max_lots": max_lots}
