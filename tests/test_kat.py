"""Known-answer test: the event-level simulation agrees with the closed form; determinism."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from ceiling import Params, accuracy
from simulate import expected_accuracy, simulate, standard_error

ROOT = Path(__file__).resolve().parent.parent

CASES = [
    Params(R=0.8, G=0.7, d_g=0.4, d_r=0.6, c=0.5, k=3),
    Params(R=0.8, G=0.7, d_g=0.4, d_r=0.6, c=0.5, k=3, r=0.5, e=0.1, f=0.05, b=0.3, G0=0.1),
    Params(R=0.9, G=0.6, d_g=0.5, d_r=0.5, c=0.4, k=5, r=0.2, e=0.2, f=0.3, b=0.6, G0=0.2),
]


@pytest.mark.parametrize("p", CASES)
def test_simulation_matches_closed_form(p):
    """Mean of 100k simulated questions within 4 standard errors of the closed form."""
    n = 100_000
    a = accuracy(p)
    assert abs(simulate(p, n, 123) - a) < 4 * standard_error(a, n)


def test_heterogeneous_simulation_matches_expectation():
    """With correlated per-question difficulty the simulation matches E[A(p_i)]."""
    p = CASES[1]
    n = 100_000
    e = expected_accuracy(p, n, 5, 1.0, 0.6)
    assert abs(simulate(p, n, 5, 1.0, 0.6) - e) < 4 * standard_error(e, n)


def test_simulation_is_deterministic():
    """Same seed, same result."""
    assert simulate(CASES[2], 20_000, 9) == simulate(CASES[2], 20_000, 9)


def test_analysis_regenerates_sealed_results(tmp_path):
    """Re-running the analysis reproduces output/results.json byte for byte."""
    subprocess.run(
        [sys.executable, str(ROOT / "code" / "analysis.py"), "--out", str(tmp_path)],
        check=True,
        capture_output=True,
    )
    new = (tmp_path / "results.json").read_bytes()
    assert new == (ROOT / "output" / "results.json").read_bytes()
    assert json.loads(new)["checks"]["kat_max_abs_z"] < 4.0
