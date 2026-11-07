#!/usr/bin/env python3
"""Compute every number the companion article cites and write ``output/results.json``.

Three blocks:

1. ``linkedin``: arithmetic read of the published ablation (``data/linkedin_ablation.json``):
   visible errors (``100 - compile``), the identified range of silent errors S (queries that
   compile but are not rated correct or almost correct): ``max(0, compile - score_4plus) <= S <=
   min(compile, 100 - score_4plus)``, valid without assuming that every query rated 4+ compiles,
   component deltas and the implied bound on the share of compile-flagged errors that the fixer
   turned into correct answers.
2. ``model``: closed-form scenarios of :mod:`ceiling` (illustrative parameters, never fitted to the
   case) for the ceiling, its invariance in the number of rounds and the silencing term.
3. ``checks``: the event-level Monte Carlo against the closed form (known-answer test) and the
   covariance identity for heterogeneous questions.

Usage: ``python3 code/analysis.py --out output`` (writes ``<out>/results.json``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ceiling import (  # noqa: E402
    Params,
    accuracy,
    ceiling,
    components,
    fix_probability,
    invisible_mass,
    no_correction,
    survival,
)
from simulate import draw_question_params, expected_accuracy, simulate, standard_error  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "linkedin_ablation.json"

# Illustrative scenario: orders of magnitude only (R near the published table recall of the full
# configuration; c and e chosen to contrast a semantic fixer with a compile-only fixer). These are
# NOT estimates of the LinkedIn system.
BASE = Params(R=0.78, G=0.60, d_g=0.45, d_r=0.60, c=0.50, k=2, r=0.30)
FIXERS = {
    "semantic_fixer": {"c": 0.50, "e": 0.05},
    "compile_only_fixer": {"c": 0.03, "e": 0.90},
}
KAT_CASES = [
    Params(R=0.8, G=0.7, d_g=0.4, d_r=0.6, c=0.5, k=3),
    Params(R=0.8, G=0.7, d_g=0.4, d_r=0.6, c=0.5, k=3, r=0.5, e=0.1, f=0.05, b=0.3, G0=0.1),
    Params(R=0.6, G=0.5, d_g=0.2, d_r=0.9, c=0.9, k=10, r=0.3),
    Params(R=0.9, G=0.6, d_g=0.5, d_r=0.5, c=0.4, k=5, r=0.2, e=0.2, f=0.3, b=0.6, G0=0.2),
]
KAT_N = 200_000
KAT_SEEDS = (20251109, 20251110)


def _row(table: dict, key: str) -> dict:
    """Return one ablation row as a dict keyed by column name."""
    return dict(zip(table["columns"], table["rows"][key]["values"], strict=True))


def linkedin_block(table: dict) -> dict:
    """Return the arithmetic read of the published ablation.

    Parameters
    ----------
    table : dict
        Parsed ``data/linkedin_ablation.json``.

    Returns
    -------
    dict
        Per-configuration error split and the component deltas.
    """
    rows = {}
    for key in table["rows"]:
        v = _row(table, key)
        rows[key] = {
            "score_4plus": v["score_4plus"],
            "compile": v["compile"],
            "visible_error": 100 - v["compile"],
            "silent_error_lower_bound": max(0, v["compile"] - v["score_4plus"]),
            # Partial identification (no assumption about queries rated 4+ that do not compile):
            # S = P(compiles and not rated 4+) lies in [max(0, C - Q), min(C, 100 - Q)].
            "silent_error_upper_bound": min(v["compile"], 100 - v["score_4plus"]),
            # The same range when each published integer may be off by up to half a point.
            "silent_error_lower_bound_rounding": max(0.0, v["compile"] - v["score_4plus"] - 1.0),
            "silent_error_upper_bound_rounding": min(v["compile"] + 0.5, 100.5 - v["score_4plus"]),
        }

    def delta(a: str, b: str) -> dict:
        """Return the change in compile, score and silent error from row ``a`` to row ``b``."""
        return {
            "from": a,
            "to": b,
            "d_compile_pp": rows[b]["compile"] - rows[a]["compile"],
            "d_score_pp": rows[b]["score_4plus"] - rows[a]["score_4plus"],
            "d_silent_lb_pp": rows[b]["silent_error_lower_bound"]
            - rows[a]["silent_error_lower_bound"],
            # Identified range of the change in S: worst and best cases of the two intervals.
            "d_silent_min_pp": rows[b]["silent_error_lower_bound"]
            - rows[a]["silent_error_upper_bound"],
            "d_silent_max_pp": rows[b]["silent_error_upper_bound"]
            - rows[a]["silent_error_lower_bound"],
            "d_silent_min_rounding_pp": rows[b]["silent_error_lower_bound_rounding"]
            - rows[a]["silent_error_upper_bound_rounding"],
            "d_silent_max_rounding_pp": rows[b]["silent_error_upper_bound_rounding"]
            - rows[a]["silent_error_lower_bound_rounding"],
        }

    deltas = {
        "query_fixer": delta("B.2", "B.3"),
        "researcher_agent": delta("B.3", "Full"),
        "rankers": delta("B.1", "B.2"),
        "modeling_components": delta("B.1", "Full"),
        "knowledge_graph": delta("A.1", "A.4"),
    }
    # Published values are integers, so the true score change of the fixer lies within +-1 pp of
    # the published difference. Upper bound on the share of compile-flagged queries the fixer
    # turned into correct ones: (d_score + 1) / d_compile.
    fx = deltas["query_fixer"]
    fixed_to_correct_max = (fx["d_score_pp"] + 1) / fx["d_compile_pp"]
    # Descriptive association across the 13 ablation configurations; they share components, so
    # this is not a causal effect.
    m = np.array([table["rows"][k]["values"] for k in table["rows"]], dtype=float)
    col = table["columns"].index
    corr = {
        "compile_vs_score": round(
            float(np.corrcoef(m[:, col("compile")], m[:, col("score_4plus")])[0, 1]), 2
        ),
        "table_recall_vs_score": round(
            float(np.corrcoef(m[:, col("table_recall")], m[:, col("score_4plus")])[0, 1]), 2
        ),
    }
    return {
        "rows": rows,
        "deltas": deltas,
        "correlations_13_configs": corr,
        "fixer_fixed_to_correct_share_max": round(fixed_to_correct_max, 4),
        "fixer_silenced_share_min": round(1.0 - fixed_to_correct_max, 4),
        "expert_review": table["expert_review"],
        "deployment": table["deployment"],
        "correction_loop_max_rounds": table["correction_loop_max_rounds"]["value"],
    }


def model_block() -> dict:
    """Return closed-form scenarios that illustrate the proposition and its corollaries."""
    out: dict = {"base": BASE.__dict__.copy(), "fixers": {}}
    for name, ch in FIXERS.items():
        p = BASE.with_(**ch)
        by_k = {k: round(accuracy(p.with_(k=k)), 4) for k in (0, 1, 2, 3, 5, 10, 50)}
        silent = {
            k: round(
                1.0 - accuracy(p.with_(k=k)) - _still_flagged(p.with_(k=k)),
                4,
            )
            for k in (0, 1, 2, 3, 5, 10, 50)
        }
        out["fixers"][name] = {
            "params": ch,
            "accuracy_by_rounds": by_k,
            "silent_error_by_rounds": silent,
            "ceiling": round(ceiling(p), 4),
            "invisible_mass": round(invisible_mass(p), 4),
            "no_correction": round(no_correction(p), 4),
        }
    lin = BASE.with_(r=0.0)
    out["linear_ceiling"] = round(ceiling(lin), 4)
    out["return_ceiling"] = round(ceiling(BASE), 4)
    out["ceiling_minus_no_correction_linear"] = round(ceiling(lin) - no_correction(lin), 4)
    fp = BASE.with_(**FIXERS["compile_only_fixer"], f=0.10, b=0.50)
    out["false_positive_best_rounds"] = _best_k(fp)
    return out


def _still_flagged(p: Params) -> float:
    """Return the probability that an error is still flagged after ``k`` rounds (visible)."""
    s_g = p.c + p.e
    s_r = p.r * p.c + p.e
    left_g = (1.0 - s_g) ** p.k if p.k else 1.0
    left_r = (1.0 - s_r) ** p.k if p.k else 1.0
    return p.R * (1.0 - p.G) * p.d_g * left_g + (1.0 - p.R) * (1.0 - p.G0) * p.d_r * left_r


def _best_k(p: Params, k_max: int = 20) -> dict:
    """Return the accuracy by rounds and the best number of rounds under false positives."""
    acc = [accuracy(p.with_(k=k)) for k in range(k_max + 1)]
    best = int(np.argmax(acc))
    return {"best_k": best, "accuracy_best": round(acc[best], 4), "accuracy_k20": round(acc[-1], 4)}


def checks_block() -> dict:
    """Return the known-answer test of the simulation and the covariance identity."""
    kat = []
    for i, p in enumerate(KAT_CASES):
        a = accuracy(p)
        for seed in KAT_SEEDS:
            s = simulate(p, KAT_N, seed)
            kat.append(
                {
                    "case": i,
                    "seed": seed,
                    "closed": round(a, 6),
                    "mc": round(s, 6),
                    "z": round((s - a) / standard_error(a, KAT_N), 3),
                }
            )
    p = KAT_CASES[1]
    cov_rows = []
    for rho in (0.0, 0.6):
        n, seed = 400_000, 7
        e = expected_accuracy(p, n, seed, 1.0, rho)
        r_i, g_i = draw_question_params(p, n, 1.0, rho, np.random.default_rng(seed))
        plug = accuracy(p.with_(R=float(r_i.mean()), G=float(g_i.mean())))
        coef = survival(p.f, p.b, p.k) - p.d_g * fix_probability(p.c, p.e, p.k)
        cov = float(np.mean(r_i * g_i) - r_i.mean() * g_i.mean())
        cov_rows.append(
            {
                "rho": rho,
                "expected": round(e, 6),
                "plug_in_means": round(plug, 6),
                "cov_identity": round(cov * coef, 6),
            }
        )
    return {
        "kat": kat,
        "kat_max_abs_z": max(abs(r["z"]) for r in kat),
        "covariance_identity": cov_rows,
        "components_sum_check": abs(sum(components(KAT_CASES[1]).values()) - accuracy(KAT_CASES[1]))
        < 1e-12,
    }


def main(argv: list[str] | None = None) -> int:
    """Write ``results.json`` into the output directory; return 0."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(ROOT / "output"))
    args = ap.parse_args(argv)
    table = json.loads(DATA.read_text(encoding="utf-8"))
    res = {"linkedin": linkedin_block(table), "model": model_block(), "checks": checks_block()}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(
        json.dumps(res, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"wrote {out / 'results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
