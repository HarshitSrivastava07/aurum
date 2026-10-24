"""Hypothetical, backend-calculated examples; never observations or trade advice."""
from .genome import normalize


def compare_hypothetical_quotes(goldm_quote: float = 100000, goldten_quote: float = 101000) -> dict:
    """Explain common metal units without asserting date-effective MCX rules.

    These assumptions are deliberately local to the educational example and do
    not enter the contract registry, imported observations or research verdict.
    The canonical Genome function performs the same fine-gram normalization as
    research; a 10g .999 reference contains 9.99 fine grams.
    """
    mini = {"trading_unit_g": 100, "quotation_unit_g": 10, "purity": .995,
            "verified": False, "spec_id": "hypothetical-education-goldm"}
    ten = {"trading_unit_g": 10, "quotation_unit_g": 10, "purity": .999,
           "verified": False, "spec_id": "hypothetical-education-goldten"}
    target_fine_grams = 10 * .999

    def leg(quote, spec):
        normalized = normalize(quote, spec)
        return {"original_per_10g": normalized["raw"],
                "purity_adjusted_per_10g": normalized["purity_adjusted"] * target_fine_grams,
                "source_purity": spec["purity"], "target_purity": .999,
                "assumed_trading_unit_g": spec["trading_unit_g"],
                "assumed_quotation_unit_g": spec["quotation_unit_g"]}

    goldm, goldten = leg(goldm_quote, mini), leg(goldten_quote, ten)
    return {"status": "hypothetical_education", "provenance": "HYPOTHETICAL EDUCATIONAL EXAMPLE",
            "unit": "INR per 10g at 999 fineness", "goldm": goldm, "goldten": goldten,
            "raw_difference_per_10g": goldten["original_per_10g"] - goldm["original_per_10g"],
            "difference": goldten["purity_adjusted_per_10g"] - goldm["purity_adjusted_per_10g"],
            "difference_direction": "GOLDTEN minus GOLDM on the common 999-fineness basis",
            "formula": "GOLDM quote x 999 / 995; compare with GOLDTEN quote",
            "limitations": [
                "Illustrative quotes and 995/999 purity assumptions only; not imported MCX market observations or date-effective verified contract specifications.",
                "Proportional fine-metal normalization is an explanatory assumption, not a valuation of purity premiums.",
                "Maturity, financing, taxes, location, delivery terms, liquidity and two-leg execution are not valued in this example.",
                "A remaining price difference is not an arbitrage certification or a recommendation to trade.",
            ]}
