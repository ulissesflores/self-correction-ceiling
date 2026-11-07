"""Event-level Monte Carlo of the pipeline, used as a known-answer test of :mod:`ceiling`.

The simulation draws, question by question, every stage outcome of the mechanism described in
:mod:`ceiling` (retrieval, generation, validator flags, correction rounds, false positives) and
records whether the final query is correct. It never calls the closed form. Its mean must match
:func:`ceiling.accuracy` within sampling error; that is the known-answer test.

Heterogeneity across questions: per-question probabilities ``R_i`` and ``G_i`` are drawn on the
logit scale around the population values with spread ``sigma`` and correlation ``rho`` between
the two latent difficulties. With ``sigma > 0`` the population accuracy is ``E[A(p_i)]``, which
differs from ``A(E[p_i])`` when ``R_i`` and ``G_i`` co-vary (hard questions are hard at both
stages). :func:`expected_accuracy` computes ``E[A(p_i)]`` exactly from the same draws.
"""

from __future__ import annotations

import numpy as np

from ceiling import Params, accuracy, survival


def _logit(x: float) -> float:
    """Return log(x / (1 - x)), clipping x away from 0 and 1."""
    x = min(max(x, 1e-9), 1.0 - 1e-9)
    return float(np.log(x / (1.0 - x)))


def draw_question_params(
    p: Params, n: int, sigma: float, rho: float, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray]:
    """Draw per-question retrieval and generation probabilities.

    Parameters
    ----------
    p : Params
        Population parameters; ``R`` and ``G`` are the logit-scale centres.
    n : int
        Number of questions.
    sigma : float
        Standard deviation of the logit-scale latent difficulty (0 = homogeneous).
    rho : float
        Correlation between the two latent difficulties, in [-1, 1].
    rng : numpy.random.Generator
        Random generator.

    Returns
    -------
    tuple of numpy.ndarray
        Arrays ``R_i`` and ``G_i`` of length ``n``.
    """
    if sigma == 0.0:
        return np.full(n, p.R), np.full(n, p.G)
    z1 = rng.standard_normal(n)
    z2 = rho * z1 + np.sqrt(max(0.0, 1.0 - rho * rho)) * rng.standard_normal(n)
    r_i = 1.0 / (1.0 + np.exp(-(_logit(p.R) + sigma * z1)))
    g_i = 1.0 / (1.0 + np.exp(-(_logit(p.G) + sigma * z2)))
    return r_i, g_i


def simulate(p: Params, n: int, seed: int, sigma: float = 0.0, rho: float = 0.0) -> float:
    """Simulate ``n`` questions event by event and return the fraction answered correctly.

    Parameters
    ----------
    p : Params
        Population parameters.
    n : int
        Number of simulated questions.
    seed : int
        Seed of ``numpy.random.default_rng``.
    sigma, rho : float
        Heterogeneity spread and correlation (see :func:`draw_question_params`).

    Returns
    -------
    float
        Fraction of questions whose final query is correct.
    """
    rng = np.random.default_rng(seed)
    r_i, g_i = draw_question_params(p, n, sigma, rho, rng)
    right_ctx = rng.random(n) < r_i
    correct = np.where(right_ctx, rng.random(n) < g_i, rng.random(n) < p.G0)
    # state: 0 correct and accepted, 4 correct awaiting a check, 1 flagged error (generation),
    # 2 flagged error (retrieval), 3 error the validator no longer sees
    state = np.full(n, 3, dtype=np.int8)
    state[correct] = 4
    wrong = ~correct
    flag_draw = rng.random(n)
    state[wrong & right_ctx & (flag_draw < p.d_g)] = 1
    state[wrong & ~right_ctx & (flag_draw < p.d_r)] = 2
    q_r = p.r * p.c
    for _ in range(p.k):
        u = rng.random(n)
        # correct query awaiting a check: passes w.p. 1-f; a false flag breaks it w.p. b
        chk = state == 4
        flagged = chk & (u < p.f)
        broken = flagged & (rng.random(n) < p.b)
        passed = chk & ~flagged
        # flagged generation error: fix w.p. c, invisible w.p. e, else stays flagged
        g = state == 1
        fix_g = g & (u < p.c)
        lost_g = g & (u >= p.c) & (u < p.c + p.e)
        # flagged retrieval error: fix needs a return to retrieval (r) and a fix (c)
        rr = state == 2
        fix_r = rr & (u < q_r)
        lost_r = rr & (u >= q_r) & (u < q_r + p.e)
        state[broken | lost_g | lost_r] = 3
        state[passed | fix_g | fix_r] = 0
    return float(np.mean((state == 0) | (state == 4)))


def expected_accuracy(p: Params, n: int, seed: int, sigma: float, rho: float) -> float:
    """Return ``E[A(p_i)]`` over per-question parameters drawn as in :func:`simulate`.

    Uses the closed form question by question (no event sampling), so its only error is the
    finite sample of question difficulties.

    Parameters
    ----------
    p : Params
        Population parameters.
    n : int
        Number of question draws.
    seed : int
        Seed of ``numpy.random.default_rng``.
    sigma, rho : float
        Heterogeneity spread and correlation.

    Returns
    -------
    float
        Mean closed-form accuracy over the drawn questions.
    """
    rng = np.random.default_rng(seed)
    r_i, g_i = draw_question_params(p, n, sigma, rho, rng)
    # accuracy is linear in R*G, R and G separately; evaluate it vectorially via components
    q_g = _fix(p.c, p.e, p.k)
    q_r = _fix(p.r * p.c, p.e, p.k)
    survive = survival(p.f, p.b, p.k)
    acc = (
        r_i * g_i * survive
        + r_i * (1.0 - g_i) * p.d_g * q_g
        + (1.0 - r_i) * p.G0 * survive
        + (1.0 - r_i) * (1.0 - p.G0) * p.d_r * q_r
    )
    return float(np.mean(acc))


def _fix(q: float, e: float, k: int) -> float:
    """Return the fix probability within ``k`` rounds (same formula as the closed form)."""
    from ceiling import fix_probability

    return fix_probability(q, e, k)


def standard_error(a: float, n: int) -> float:
    """Return the binomial standard error ``sqrt(a (1 - a) / n)`` of a simulated fraction."""
    return float(np.sqrt(max(a * (1.0 - a), 1e-12) / n))


__all__ = [
    "accuracy",
    "draw_question_params",
    "expected_accuracy",
    "simulate",
    "standard_error",
]
