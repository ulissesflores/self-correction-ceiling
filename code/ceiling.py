"""Closed-form accuracy of a retrieve -> generate -> validate -> correct pipeline.

The model describes one question answered by an agentic text-to-SQL pipeline:

1. a retrieval stage puts the right tables and fields in context with probability ``R``;
2. a generation stage writes a correct query with probability ``G`` given the right context,
   and with probability ``G0`` given the wrong context (a valid alternative table);
3. a deterministic validator (``EXPLAIN``, field existence, execution error) flags a wrong
   query built on the right context with probability ``d_g`` and a wrong query built on the
   wrong context with probability ``d_r``; it flags a correct query (false positive) with
   probability ``f`` per round;
4. a corrector gets up to ``k`` rounds. Each round on a flagged generation error fixes it with
   probability ``c``, turns it into an error the validator can no longer see with probability
   ``e``, and otherwise leaves it flagged. A flagged retrieval error is fixed only if the
   corrector also goes back to retrieval, which happens with probability ``r`` per round, so its
   per-round fix probability is ``r * c``. A successful fix ends the loop (the fixed query
   is accepted). A correct query is re-checked each round until it passes: when falsely
   flagged, the correction breaks it with probability ``b`` (the broken query is never flagged
   again, conservative) and otherwise leaves it correct for the next check.

``accuracy`` is the probability that the final query is correct. ``ceiling`` is its supremum
over every corrector (any ``c``, ``k``) and equals one minus the mass of errors the validator
never sees. The linear pipeline of the literature is the special case ``r = 0``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace


@dataclass(frozen=True)
class Params:
    """Parameters of the pipeline model; every probability lies in [0, 1].

    Attributes
    ----------
    R : float
        Probability that retrieval puts the right tables and fields in context.
    G : float
        Probability of a correct query given the right context.
    d_g : float
        Probability that the validator flags a wrong query built on the right context.
    d_r : float
        Probability that the validator flags a wrong query built on the wrong context.
    c : float
        Per-round probability that the corrector fixes a flagged error it can reach.
    k : int
        Maximum number of correction rounds (``k = 0`` means no corrector).
    r : float
        Per-round probability that a correction goes back to retrieval (0 = linear pipeline).
    e : float
        Per-round probability that a correction turns a flagged error into an unflagged one.
    f : float
        Per-round probability that the validator flags a correct query (false positive).
    b : float
        Probability that a correction triggered by a false positive breaks the correct query.
    G0 : float
        Probability of a correct query given the wrong context.
    """

    R: float
    G: float
    d_g: float
    d_r: float
    c: float
    k: int
    r: float = 0.0
    e: float = 0.0
    f: float = 0.0
    b: float = 0.0
    G0: float = 0.0

    def __post_init__(self) -> None:
        """Reject parameters outside their domain."""
        for name, value in asdict(self).items():
            if name == "k":
                if not isinstance(value, int) or value < 0:
                    raise ValueError(f"k must be a non-negative integer, got {value!r}")
            elif not 0.0 <= float(value) <= 1.0:
                raise ValueError(f"{name} must lie in [0, 1], got {value!r}")
        if self.c + self.e > 1.0 + 1e-12:
            raise ValueError(f"c + e must not exceed 1, got {self.c + self.e!r}")

    def with_(self, **changes: float) -> Params:
        """Return a copy with some parameters replaced."""
        return replace(self, **changes)


def fix_probability(q: float, e: float, k: int) -> float:
    """Return the probability that a flagged error is fixed within ``k`` rounds.

    Each round fixes with probability ``q``, makes the error invisible with probability ``e``
    (absorbing: the loop stops) and otherwise leaves it flagged. The absorbing Markov chain gives
    ``q / (q + e) * (1 - (1 - q - e) ** k)``.

    Parameters
    ----------
    q : float
        Per-round fix probability.
    e : float
        Per-round probability of turning the error invisible.
    k : int
        Number of rounds.

    Returns
    -------
    float
        Probability of a fix within ``k`` rounds; 0 when ``q + e == 0`` or ``k == 0``.
    """
    s = q + e
    if s <= 0.0 or k == 0:
        return 0.0
    return q / s * (1.0 - (1.0 - s) ** k)


def survival(f: float, b: float, k: int) -> float:
    """Return the probability that a correct query survives ``k`` checks with false positives.

    Each check passes it (loop ends) with probability ``1 - f``; a false flag breaks it with
    probability ``b`` and otherwise keeps it for the next check. The query is broken with
    probability ``f b (1 - (f (1 - b)) ** k) / (1 - f (1 - b))``.

    Parameters
    ----------
    f : float
        Per-check false-positive probability.
    b : float
        Probability that a correction triggered by a false positive breaks the query.
    k : int
        Number of checks (rounds).

    Returns
    -------
    float
        Survival probability; 1 when ``f * b == 0`` or ``k == 0``.
    """
    loop = f * (1.0 - b)
    if f * b == 0.0 or k == 0:
        return 1.0
    if loop >= 1.0:  # f = 1 and b = 0 is excluded above; loop < 1 otherwise
        return 1.0
    return 1.0 - f * b * (1.0 - loop**k) / (1.0 - loop)


def components(p: Params) -> dict[str, float]:
    """Return the four additive parts of the final accuracy.

    Parameters
    ----------
    p : Params
        Model parameters.

    Returns
    -------
    dict
        ``kept_correct`` (right context, correct, survives false positives), ``fixed_generation``
        (right context, wrong, flagged and fixed), ``lucky_wrong_context`` (wrong context but a
        valid alternative) and ``fixed_retrieval`` (wrong context, flagged and fixed through a
        return to retrieval). Their sum is :func:`accuracy`.
    """
    survive = survival(p.f, p.b, p.k)
    return {
        "kept_correct": p.R * p.G * survive,
        "fixed_generation": p.R * (1.0 - p.G) * p.d_g * fix_probability(p.c, p.e, p.k),
        "lucky_wrong_context": (1.0 - p.R) * p.G0 * survive,
        "fixed_retrieval": (1.0 - p.R)
        * (1.0 - p.G0)
        * p.d_r
        * fix_probability(p.r * p.c, p.e, p.k),
    }


def accuracy(p: Params) -> float:
    """Return the probability that the final query is correct.

    Parameters
    ----------
    p : Params
        Model parameters.

    Returns
    -------
    float
        Final accuracy, the sum of :func:`components`.
    """
    return sum(components(p).values())


def no_correction(p: Params) -> float:
    """Return the accuracy without any corrector (``k = 0``): ``R*G + (1-R)*G0``."""
    return accuracy(p.with_(k=0))


def invisible_mass(p: Params) -> float:
    """Return the probability mass of errors the validator never flags.

    ``U = R (1 - G)(1 - d_g) + (1 - R)(1 - G0)(1 - d_r)``. No corrector can reach these errors.
    """
    return p.R * (1.0 - p.G) * (1.0 - p.d_g) + (1.0 - p.R) * (1.0 - p.G0) * (1.0 - p.d_r)


def ceiling(p: Params) -> float:
    """Return the supremum of the accuracy over every corrector (any ``c``, ``k``, with e=f=0).

    With a return to retrieval (``r > 0``) the ceiling is ``1 - U`` (:func:`invisible_mass`).
    Without it (``r = 0``) the flagged retrieval errors are unreachable too, and the ceiling is
    ``R [G + (1 - G) d_g] + (1 - R) G0``: the linear-pipeline bound.

    Parameters
    ----------
    p : Params
        Model parameters; ``c``, ``k``, ``e``, ``f`` and ``b`` are ignored.

    Returns
    -------
    float
        Ceiling of the final accuracy.
    """
    reach_r = 1.0 if p.r > 0.0 else 0.0
    return (
        p.R * (p.G + (1.0 - p.G) * p.d_g)
        + (1.0 - p.R) * p.G0
        + (1.0 - p.R) * (1.0 - p.G0) * p.d_r * reach_r
    )


def max_correction_gain(p: Params) -> float:
    """Return the largest gain any corrector can add to the no-correction accuracy.

    ``ceiling(p) - no_correction(p)``; for the linear pipeline this is ``R (1 - G) d_g``.
    """
    return ceiling(p) - no_correction(p)


def best_rounds(p: Params, k_max: int = 50) -> tuple[int, float]:
    """Return the number of rounds that maximizes accuracy and that accuracy.

    With false positives (``f * b > 0``) more rounds can lower accuracy, so the best ``k`` is
    finite; ties resolve to the smallest ``k``.

    Parameters
    ----------
    p : Params
        Model parameters (``k`` is ignored).
    k_max : int
        Largest number of rounds searched.

    Returns
    -------
    tuple of (int, float)
        The best ``k`` in ``0..k_max`` and the accuracy it reaches.
    """
    best_k, best_a = 0, accuracy(p.with_(k=0))
    for k in range(1, k_max + 1):
        a = accuracy(p.with_(k=k))
        if a > best_a + 1e-15:
            best_k, best_a = k, a
    return best_k, best_a


def sensitivities(p: Params) -> dict[str, float]:
    """Return the partial derivatives of the ceiling and of the finite-``k`` accuracy.

    The ceiling depends on ``R``, ``G``, ``d_g`` and ``d_r`` but not on ``c``; the finite-round
    accuracy depends on ``c``. Derivatives are central finite differences (step 1e-6), clipped
    to the domain.

    Parameters
    ----------
    p : Params
        Model parameters.

    Returns
    -------
    dict
        Keys ``dceiling_d<name>`` and ``daccuracy_d<name>`` for name in R, G, d_g, d_r, c.
    """
    out: dict[str, float] = {}
    h = 1e-6
    for name in ("R", "G", "d_g", "d_r", "c"):
        v = getattr(p, name)
        lo, hi = max(0.0, v - h), min(1.0 - (p.e if name == "c" else 0.0), v + h)
        plo, phi = p.with_(**{name: lo}), p.with_(**{name: hi})
        out[f"dceiling_d{name}"] = (ceiling(phi) - ceiling(plo)) / (hi - lo)
        out[f"daccuracy_d{name}"] = (accuracy(phi) - accuracy(plo)) / (hi - lo)
    return out
