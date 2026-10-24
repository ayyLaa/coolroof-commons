"""Presentation-ready conclusion for the satellite evidence.

Every number in the text is taken from the corrected cases, and the verdict depends on
whether anything survives correction, so rerunning on new data cannot leave a stale
claim behind. The untested explanations are listed as hypotheses: nothing in this
analysis measures them.
"""

from __future__ import annotations

from collections.abc import Sequence

UNTESTED_EXPLANATIONS = (
    "Emissivity: bright bare-metal roofs have a low thermal emissivity, so they shed heat "
    "poorly and the satellite retrieval, which assumes a generic emissivity, misreads "
    "their temperature; albedo alone does not decide the measured LST.",
    "Albedo error: the Sentinel-2 broadband albedo is an estimate (Liang 2001 narrow-to-"
    "broadband conversion at 20 m), so some roofs may sit in the wrong albedo quartile.",
    "Seasonal median: a summer median of cloud-free scenes smooths out the hot-day "
    "differences that a cool roof is meant to reduce.",
    "Location: the dark and bright groups are different buildings in different places, so "
    "neighbourhood, height and construction differences are mixed into the comparison.",
)
ROOF_LEVEL_VERDICT = (
    "Satellite data is not sufficient for roof-level verification; it is sufficient for "
    "targeting."
)
SIGNAL_FOUND_VERDICT = (
    "Satellite data shows a corrected roof-level signal only in {ids}; the other cases "
    "still need on-roof measurement for verification."
)


def _ids(cases: Sequence[dict]) -> list[str]:
    return [case["case_id"] for case in cases]


def _surviving(cases: Sequence[dict]) -> list[dict]:
    return [c for c in cases if c["significant_bonferroni"] or c["significant_fdr"]]


def tests_summary(cases: Sequence[dict], alpha: float) -> str:
    raw = [c for c in cases if c["significant_raw"]]
    raw_text = ", ".join(f"{c['case_id']} p={c['p_value']:.3f}" for c in raw) or "none"
    n_bonferroni = sum(c["significant_bonferroni"] for c in cases)
    n_fdr = sum(c["significant_fdr"] for c in cases)
    return (
        f"{len(cases)} cases were tested; {len(raw)} of them reached raw p < {alpha} "
        f"({raw_text}). After Bonferroni correction (alpha = {alpha}/{len(cases)} = "
        f"{alpha / len(cases):.5f}) {n_bonferroni} remain, and after Benjamini-Hochberg "
        f"FDR correction {n_fdr} remain."
    )


def resolution_finding(cases: Sequence[dict]) -> str:
    """Resolution would explain the null result only if the signal grew with coverage;
    the highest-ratio case is the direct check of that."""
    ordered = sorted(cases, key=lambda case: case["roof_to_pixel_area_ratio"])
    lowest, highest = ordered[0], ordered[-1]
    span = (
        f"The roof-to-pixel area ratio rose from {lowest['roof_to_pixel_area_ratio']} "
        f"({lowest['case_id']}) to {highest['roof_to_pixel_area_ratio']} "
        f"({highest['case_id']}, p={highest['p_value']:.2f})"
    )
    surviving = _surviving(cases)
    if not surviving:
        return (
            f"{span}, yet the signal did not strengthen: no case is significant after "
            "correction. Resolution is therefore not the only problem."
        )
    ratios = ", ".join(f"{c['case_id']} {c['roof_to_pixel_area_ratio']}" for c in surviving)
    return f"{span}. Cases significant after correction, with their ratios: {ratios}."


def build_conclusion(cases: Sequence[dict], alpha: float) -> dict:
    surviving = _surviving(cases)
    verdict = (
        SIGNAL_FOUND_VERDICT.format(ids=", ".join(_ids(surviving)))
        if surviving
        else ROOF_LEVEL_VERDICT
    )
    summary, resolution = tests_summary(cases, alpha), resolution_finding(cases)
    explanations = " ".join(UNTESTED_EXPLANATIONS)
    return {
        "n_cases_tested": len(cases),
        "n_significant_raw": sum(c["significant_raw"] for c in cases),
        "n_significant_bonferroni": sum(c["significant_bonferroni"] for c in cases),
        "n_significant_fdr": sum(c["significant_fdr"] for c in cases),
        "raw_significant_case_ids": _ids([c for c in cases if c["significant_raw"]]),
        "surviving_case_ids": _ids(surviving),
        "tests_summary": summary,
        "resolution_finding": resolution,
        "untested_explanations": list(UNTESTED_EXPLANATIONS),
        "verdict": verdict,
        "text": (
            f"{summary} {resolution} Possible causes not tested here: {explanations} "
            f"{verdict}"
        ),
    }
