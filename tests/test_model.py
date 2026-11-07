"""Properties of the closed-form model: the proposition and its corollaries."""

from __future__ import annotations

import itertools

import pytest

from ceiling import (
    Params,
    accuracy,
    ceiling,
    components,
    fix_probability,
    invisible_mass,
    max_correction_gain,
    no_correction,
    survival,
)

GRID = [
    Params(R=R, G=G, d_g=dg, d_r=dr, c=c, k=k, r=r, e=e, f=f, b=b, G0=g0)
    for R, G, dg, dr, c, k, r, e, f, b, g0 in itertools.product(
        (0.3, 0.8, 1.0),
        (0.2, 0.7),
        (0.0, 0.5, 1.0),
        (0.0, 0.6),
        (0.0, 0.4, 0.9),
        (0, 1, 2, 10),
        (0.0, 0.5),
        (0.0, 0.1),
        (0.0, 0.2),
        (0.0, 0.5),
        (0.0, 0.1),
    )
    if c + e <= 1.0
]


@pytest.mark.parametrize("p", GRID[::7])
def test_accuracy_never_exceeds_ceiling(p):
    """Proposition 1: no corrector (any c, e, k, f, b) crosses the ceiling."""
    assert accuracy(p) <= ceiling(p) + 1e-12


@pytest.mark.parametrize("p", GRID[::11])
def test_ceiling_with_return_is_one_minus_invisible_mass(p):
    """With a return to retrieval the ceiling equals 1 - U."""
    if p.r > 0:
        assert ceiling(p) == pytest.approx(1.0 - invisible_mass(p), abs=1e-12)


def test_linear_special_case():
    """Corollary 2: without a return to retrieval the ceiling is R[G + (1-G)d_g] + (1-R)G0."""
    p = Params(R=0.78, G=0.6, d_g=0.45, d_r=0.6, c=0.5, k=2, r=0.0)
    assert ceiling(p) == pytest.approx(0.78 * (0.6 + 0.4 * 0.45))
    assert max_correction_gain(p) == pytest.approx(0.78 * 0.4 * 0.45)


def test_rounds_converge_to_ceiling_without_losses():
    """Corollary 1: with e = f = 0 and c > 0 accuracy rises with k and tends to the ceiling."""
    p = Params(R=0.78, G=0.6, d_g=0.45, d_r=0.6, c=0.5, k=0, r=0.3)
    acc = [accuracy(p.with_(k=k)) for k in range(0, 200)]
    assert all(b >= a - 1e-15 for a, b in itertools.pairwise(acc))
    assert acc[-1] == pytest.approx(ceiling(p), abs=1e-6)


def test_corrector_only_changes_speed_not_ceiling():
    """The ceiling does not depend on c; the finite-round accuracy does."""
    p = Params(R=0.78, G=0.6, d_g=0.45, d_r=0.6, c=0.1, k=2, r=0.3)
    q = p.with_(c=0.9)
    assert ceiling(p) == ceiling(q)
    assert accuracy(q) > accuracy(p)


def test_silencing_caps_below_ceiling():
    """With e > 0 the limit is strictly below the ceiling: c / (c + e) of flagged errors."""
    p = Params(R=1.0, G=0.5, d_g=1.0, d_r=0.0, c=0.03, k=200, e=0.9)
    assert accuracy(p) == pytest.approx(0.5 + 0.5 * 0.03 / 0.93, abs=1e-9)
    assert accuracy(p) < ceiling(p)


def test_false_positives_can_make_correction_harmful():
    """Corollary 3: a compile-only fixer with false positives is best at k = 0."""
    p = Params(R=0.78, G=0.6, d_g=0.45, d_r=0.6, c=0.03, e=0.9, k=0, r=0.3, f=0.1, b=0.5)
    assert accuracy(p.with_(k=1)) < accuracy(p.with_(k=0))


def test_fix_probability_closed_form():
    """Absorbing-chain fix probability: limits and a hand-computed value."""
    assert fix_probability(0.5, 0.0, 1) == pytest.approx(0.5)
    assert fix_probability(0.5, 0.0, 2) == pytest.approx(0.75)
    assert fix_probability(0.2, 0.2, 2) == pytest.approx(0.5 * (1 - 0.6**2))
    assert fix_probability(0.0, 0.0, 5) == 0.0


def test_survival_closed_form():
    """Survival under false positives: k = 1 equals 1 - f b; f b = 0 equals 1."""
    assert survival(0.1, 0.5, 1) == pytest.approx(1 - 0.05)
    assert survival(0.0, 0.5, 3) == 1.0
    loop = 0.1 * 0.5
    assert survival(0.1, 0.5, 2) == pytest.approx(1 - 0.05 * (1 + loop))


def test_components_sum_and_no_correction():
    """The four components add up to the accuracy; k = 0 gives R G + (1 - R) G0."""
    p = Params(R=0.7, G=0.6, d_g=0.4, d_r=0.5, c=0.5, k=3, r=0.2, e=0.1, f=0.1, b=0.2, G0=0.1)
    assert sum(components(p).values()) == pytest.approx(accuracy(p))
    assert no_correction(p) == pytest.approx(0.7 * 0.6 + 0.3 * 0.1)


@pytest.mark.parametrize(
    "bad",
    [dict(R=1.2), dict(G=-0.1), dict(k=-1), dict(c=0.8, e=0.3)],
)
def test_domain_is_enforced(bad):
    """Probabilities outside [0, 1], negative k or c + e > 1 are rejected."""
    base = dict(R=0.5, G=0.5, d_g=0.5, d_r=0.5, c=0.5, k=1)
    base.update(bad)
    with pytest.raises(ValueError):
        Params(**base)
