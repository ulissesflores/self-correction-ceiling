"""Numbers quoted in README.md and docs/THEORY.md are locked against the sealed results."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RES = json.loads((ROOT / "output" / "results.json").read_text(encoding="utf-8"))
DOCS = {name: (ROOT / name).read_text(encoding="utf-8") for name in ("README.md", "docs/THEORY.md")}


def _fmt(x: float) -> str:
    """Return ``x`` with four decimals, as the documents quote the scenario values."""
    return f"{x:.4f}"


def test_scenario_values_quoted():
    """Check that the scenario table of both documents carries the sealed values."""
    m = RES["model"]
    fx = m["fixers"]
    quoted = [
        _fmt(fx["compile_only_fixer"]["no_correction"]),
        _fmt(m["return_ceiling"]),
        _fmt(m["linear_ceiling"]),
        _fmt(fx["semantic_fixer"]["accuracy_by_rounds"]["2"]),
        _fmt(fx["compile_only_fixer"]["accuracy_by_rounds"]["2"]),
    ]
    for name, text in DOCS.items():
        for value in quoted:
            assert value in text, (name, value)


def test_case_arithmetic_quoted():
    """Check the identified ranges, the fixer deltas and the correlations quoted in both docs."""
    rows = RES["linkedin"]["rows"]
    d = RES["linkedin"]["deltas"]["query_fixer"]
    corr = RES["linkedin"]["correlations_13_configs"]
    b2 = (rows["B.2"]["silent_error_lower_bound"], rows["B.2"]["silent_error_upper_bound"])
    b3 = (rows["B.3"]["silent_error_lower_bound"], rows["B.3"]["silent_error_upper_bound"])
    assert (b2, b3) == ((29, 53), (48, 53))
    assert (d["d_compile_pp"], d["d_score_pp"]) == (19, 0)
    assert (d["d_silent_min_pp"], d["d_silent_max_pp"]) == (-5, 24)
    for name, text in DOCS.items():
        for quoted in (
            "29-53",
            "48-53",
            "-5 and +24",
            f"{corr['compile_vs_score']:.2f}",
            f"{corr['table_recall_vs_score']:.2f}",
        ):
            assert quoted in text, (name, quoted)
        assert "+19" in text or "19 points" in text, name
    assert f"{RES['checks']['kat_max_abs_z']:.3f}" in DOCS["README.md"]
    assert f"{RES['checks']['kat_max_abs_z']:.3f}" in DOCS["docs/THEORY.md"]
