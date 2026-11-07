"""Every number the article cites, locked against the sealed results and the source data."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
RES = json.loads((ROOT / "output" / "results.json").read_text(encoding="utf-8"))
DATA = json.loads((ROOT / "data" / "linkedin_ablation.json").read_text(encoding="utf-8"))
L, M, C = RES["linkedin"], RES["model"], RES["checks"]


def test_source_table_values():
    """Published Table 2 values used by the article (arXiv:2507.14372, p. 6)."""
    rows = DATA["rows"]
    cols = DATA["columns"]

    def v(k, c):
        """Return the published value of column ``c`` in row ``k``."""
        return rows[k]["values"][cols.index(c)]

    assert (v("Full", "table_recall"), v("Full", "column_recall")) == (78, 56)
    assert (v("Full", "score_4plus"), v("Full", "compile")) == (48, 96)
    assert (v("B.3", "score_4plus"), v("B.3", "compile")) == (47, 95)
    assert (v("B.2", "score_4plus"), v("B.2", "compile")) == (47, 76)
    assert (v("B.1", "score_4plus"), v("B.1", "compile")) == (46, 66)
    assert (v("A.1", "score_4plus"), v("A.4", "score_4plus")) == (9, 49)
    assert DATA["expert_review"]["share_4_or_5"] == 53
    assert DATA["expert_review"]["most_common_issue_share"] == 24
    assert DATA["deployment"]["survey_at_least_passes"] == 95
    assert DATA["correction_loop_max_rounds"]["value"] == 2


def test_silent_error_lower_bounds():
    """Silent error >= compile - score4+: 29 (no fixer) -> 48 (with fixer)."""
    assert L["rows"]["B.2"]["silent_error_lower_bound"] == 29
    assert L["rows"]["B.3"]["silent_error_lower_bound"] == 48
    assert L["rows"]["B.2"]["visible_error"] == 24
    assert L["rows"]["B.3"]["visible_error"] == 5


def test_descriptive_correlations():
    """Across the 13 ablation configurations: r(compile, 4+) 0.27; r(table recall, 4+) 0.91."""
    assert L["correlations_13_configs"] == {"compile_vs_score": 0.27, "table_recall_vs_score": 0.91}


def test_silent_error_identified_ranges():
    """Partial identification: B.2 in [29, 53], B.3 in [48, 53], change in [-5, +24] pp."""
    r = L["rows"]
    assert (r["B.2"]["silent_error_lower_bound"], r["B.2"]["silent_error_upper_bound"]) == (29, 53)
    assert (r["B.3"]["silent_error_lower_bound"], r["B.3"]["silent_error_upper_bound"]) == (48, 53)
    fx = L["deltas"]["query_fixer"]
    assert (fx["d_silent_min_pp"], fx["d_silent_max_pp"]) == (-5, 24)


def test_silent_error_ranges_with_rounding():
    """Half-point rounding of each total: B.2 [28, 53.5], B.3 [47, 53.5], change [-6.5, +25.5]."""
    r = L["rows"]
    lo, hi = "silent_error_lower_bound_rounding", "silent_error_upper_bound_rounding"
    assert (r["B.2"][lo], r["B.2"][hi]) == (28.0, 53.5)
    assert (r["B.3"][lo], r["B.3"][hi]) == (47.0, 53.5)
    fx = L["deltas"]["query_fixer"]
    assert (fx["d_silent_min_rounding_pp"], fx["d_silent_max_rounding_pp"]) == (-6.5, 25.5)


def test_component_deltas():
    """Fixer: +19 pp compile, 0 pp score; modeling: +30 / +2; knowledge graph: +8 / +40."""
    d = L["deltas"]
    assert (d["query_fixer"]["d_compile_pp"], d["query_fixer"]["d_score_pp"]) == (19, 0)
    assert (d["modeling_components"]["d_compile_pp"], d["modeling_components"]["d_score_pp"]) == (
        30,
        2,
    )
    assert (d["knowledge_graph"]["d_compile_pp"], d["knowledge_graph"]["d_score_pp"]) == (8, 40)
    assert (d["researcher_agent"]["d_compile_pp"], d["researcher_agent"]["d_score_pp"]) == (1, 1)


def test_fixer_bound():
    """At most 1/19 (5.3%) of compile-flagged queries became correct; >= 94.7% silenced."""
    assert L["fixer_fixed_to_correct_share_max"] == pytest.approx(0.0526)
    assert L["fixer_silenced_share_min"] == pytest.approx(0.9474)


def test_model_scenarios():
    """Illustrative scenario numbers quoted in the article."""
    fx = M["fixers"]
    assert fx["compile_only_fixer"]["no_correction"] == pytest.approx(0.468)
    assert fx["compile_only_fixer"]["accuracy_by_rounds"]["2"] == pytest.approx(0.4738)
    assert fx["compile_only_fixer"]["silent_error_by_rounds"]["0"] == pytest.approx(0.2596)
    assert fx["compile_only_fixer"]["silent_error_by_rounds"]["2"] == pytest.approx(0.5244)
    assert fx["semantic_fixer"]["accuracy_by_rounds"]["2"] == pytest.approx(0.6054)
    assert fx["semantic_fixer"]["ceiling"] == pytest.approx(0.7404)
    assert M["linear_ceiling"] == pytest.approx(0.6084)
    assert M["false_positive_best_rounds"]["best_k"] == 0
    assert M["false_positive_best_rounds"]["accuracy_k20"] == pytest.approx(0.4492)


def test_checks():
    """Known-answer test within 4 standard errors; covariance identity holds."""
    assert C["kat_max_abs_z"] < 4.0
    assert C["components_sum_check"] is True
    for row in C["covariance_identity"]:
        assert row["expected"] - row["plug_in_means"] == pytest.approx(
            row["cov_identity"], abs=2e-6
        )
