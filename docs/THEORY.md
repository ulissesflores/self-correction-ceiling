# Theory: the self-correction ceiling

This document states the model, its assumptions, the proposition and the corollaries that the
code in [`code/ceiling.py`](../code/ceiling.py) implements and that the tests lock. The wording is
deliberately conservative: the model is an idealisation, the scenarios are illustrative, and the
public evidence it is confronted with is consistent with it but does not prove it.

## Prior art and what is claimed

The ingredients are not new, and none is claimed as new:

- the accuracy of a model after a round of self-correction as a function of a "fix" and a
  "corruption" rate (Yang et al., 2025, EMNLP, doi:10.18653/v1/2025.emnlp-main.685; Reitich, 2026,
  arXiv:2604.18245);
- the idea that an error-handling mechanism is capped by the share of faults it can detect, called
  coverage in dependability engineering (Arnold, 1973, IEEE Trans. Computers,
  doi:10.1109/T-C.1973.223703);
- text-to-SQL pipelines whose stages (schema linking, generation, selection, correction) are
  studied one at a time (for example Maamari et al., 2024, Table Representation Learning workshop
  at NeurIPS, arXiv:2408.07702).

What this repository does is to **instantiate and compose** them for a multi-agent text-to-SQL
pipeline with a deterministic validator: an absorbing ceiling `1 - U` that separates retrieval
quality `R`, generation quality `G`, validator detection `d`, corrector strength `c`, the return
path to retrieval `r`, silencing `e` and false positives `f`, `b`; and a confrontation of that
ceiling with the numbers published for a production system (LinkedIn SQL Bot, Chen et al., 2025,
arXiv:2507.14372).

## The pipeline

One question is answered by `retrieve -> generate -> validate -> correct`:

1. Retrieval puts the right tables and fields in context with probability `R`.
2. Generation writes a correct query with probability `G` given the right context and `G0` given
   the wrong context (a valid alternative table).
3. A predominantly deterministic validator (query plan, field existence, execution error; in the case, table and column names are extracted by an LLM) flags a wrong query
   built on the right context with probability `d_g`, a wrong query built on the wrong context
   with probability `d_r`, and a correct query (false positive) with probability `f` per round.
4. A corrector gets up to `k` rounds. Each round on a flagged generation error fixes it with
   probability `c`, turns it into an error the validator can no longer see with probability `e`
   (silencing), and otherwise leaves it flagged. A flagged retrieval error is fixed only if the
   corrector goes back to retrieval, with probability `r` per round, so its per-round fix
   probability is `r c`. A fix ends the loop. A falsely flagged correct query is broken with
   probability `b` and otherwise kept for the next check; a broken query is never flagged again.

Assumptions: the stage outcomes are independent given the parameters of one question; the
validator and the corrector do not change `R`, `G` or `d` between rounds; a query the validator
does not flag is accepted. These are modelling choices, not facts about any production system.

## Closed form

Let `F(q, e, k) = q/(q + e) * (1 - (1 - q - e)^k)` be the probability that a flagged error is
fixed within `k` rounds (an absorbing Markov chain with a fix, a silencing and a stay transition),
and `S(f, b, k) = 1 - f b (1 - (f (1 - b))^k) / (1 - f (1 - b))` the probability that a correct
query survives `k` checks. The accuracy `A` is the sum of four parts:

```text
A = R G S                              (kept correct)
  + R (1 - G) d_g F(c, e, k)           (generation error flagged and fixed)
  + (1 - R) G0 S                       (valid alternative in the wrong context)
  + (1 - R)(1 - G0) d_r F(r c, e, k)   (retrieval error flagged and fixed through retrieval)
```

The Monte Carlo in [`code/simulate.py`](../code/simulate.py) draws every stage outcome question by
question without calling the closed form; the known-answer test requires the two to agree within
sampling error (maximum |z| = 2.186 over 8 runs in `output/results.json`).

## Proposition 1 (ceiling)

With `e = f = 0` and `r > 0`, for every corrector `(c, k)`:

```text
A <= 1 - U,    U = R (1 - G)(1 - d_g) + (1 - R)(1 - G0)(1 - d_r)
```

and the supremum is attained as `k -> infinity` for `c > 0`. `U` is the mass of errors the
validator never sees.

*Proof.* With `e = 0`, `F(q, 0, k) = 1 - (1 - q)^k <= 1` and `S = 1`. Replacing both `F` by 1 in
the closed form gives `R G + R (1 - G) d_g + (1 - R) G0 + (1 - R)(1 - G0) d_r`, which equals
`1 - U` by complement. For `c > 0` and `r > 0`, `F -> 1` as `k -> infinity`. QED.

## Corollaries

1. **Without silencing, the corrector changes the speed, not the ceiling.** `c` and `k` do not
   appear in `1 - U`;
   `A` is non-decreasing in `k` when `e = f = 0` and, for `c > 0` and `r > 0`, approaches `1 - U`
   at a rate set by `c` and `r c` (with `q = 0` for a class of flagged errors, that class is never
   repaired; see Corollary 2). Only `R`, `G`, `G0`, `d_g`, `d_r` move the ceiling.
2. **No return to retrieval (`r = 0`).** `F(0, 0, k) = 0`, so flagged retrieval errors are
   unreachable and the ceiling is `R [G + (1 - G) d_g] + (1 - R) G0`, the linear-pipeline bound.
3. **Silencing and false positives.** With `e > 0` the loop ends in a silent error with probability
   `e/(q + e)`, so the limit as `k -> infinity` is `c/(c + e)` of the flagged generation errors
   (and `r c/(r c + e)` of the flagged retrieval errors): the ceiling is not reached. With
   `f b > 0`, `S` decreases in `k`, so extra rounds can lower accuracy; the best `k` is finite and
   can be 0 (in the false-positive scenario of `output/results.json` the best `k` is 0).
4. **Heterogeneity identity.** If `R` and `G` vary across questions and the other parameters do not,
   `A` is bilinear in `R` and `G` with cross term `R G (S - d_g F)`, hence

   ```text
   E[A] - A(E[R], E[G]) = Cov(R, G) * (S - d_g F)
   ```

   Plugging in the population means misestimates the accuracy whenever difficulty at retrieval and
   at generation co-vary. The identity is checked numerically for `rho = 0` and `rho = 0.6`.

## Evidence from a public case (arithmetic only)

Chen et al. (2025), Table 2, report an ablation of the LinkedIn SQL Bot on an internal benchmark
(133 questions): the share of questions whose query compiles (`C`) and the share rated 4 or 5 by
an LLM judge (gpt-4o) against ground truth (`Q`). One run, no confidence intervals. The values are
copied into [`data/linkedin_ablation.json`](../data/linkedin_ablation.json).

The silent error `S` (the query compiles and is not rated 4+) is not observed: the judge receives the
question, answer, ground truth and rubric, with no execution described, so a query that does not
compile can still be rated 4+. The published totals only bound it (partial identification, Manski,
2003):

```text
max(0, C - Q) <= S <= min(C, 100 - Q)
```

The lower bound holds always; it equals `S` only if every query rated 4+ compiles. The ranges are
computed on the published integers (each total carries up to half a point of rounding).

| Step | Compile `C` | Rated 4+ `Q` | Identified range of `S` |
|---|---|---|---|
| Without the query fixer (B.2) | 76 | 47 | 29-53 |
| With the query fixer (B.3) | 95 | 47 | 48-53 |
| Change, B.2 -> B.3 | +19 pp | 0 pp | between -5 and +24 pp |
| Only schemas (A.1) -> with knowledge graph (A.4) | 88 -> 96 | 9 -> 49 | 79-88 -> 47-51 |

The firm statement is the B.3 range: with the fixer, about half of all questions get a query that
compiles without a 4+. The rise of the range is **consistent with** a fixer that converts visible
into silent errors, and equally with zero conversion (the fixed queries already rated 4+ before
they compiled); only a paired transition matrix (does not compile / compiles and wrong / compiles
and right, per question) would separate the readings. Across the 13 configurations of the
ablation, the correlation between compilation and the rated-4+ share is 0.27, against 0.91 between
table recall and that share (descriptive; the configurations share components, so this is not a
causal estimate). Configurations that differ by one component also move by up to 7 points (A.4
49, A.5 42); with one run per configuration, such a difference cannot be split into an effect of
the change and evaluation noise.

`S` is not `U`. The queries in `U` compile, so the part of `U` that is not rated 4+ lies inside
`S`; the part of `U` that the judge rates 4+ (a 4 admits an almost-correct query) is not measured.
The totals therefore bound `S` but give no upper bound on `U` beyond the trivial `100 U <= C` (`C` is a
percentage, `U` a fraction).

A secondary number needs extra assumptions: if the fixer neither broke queries that were already
correct nor made a compiling query stop compiling (untestable without paired data), at most
`1/19 = 5.3%` of the queries it moved into "compiles" can have become correct. The authors state
that their validator does not cover invalid column values, and the most common issue in their
expert review is "Filter is incorrect" (24%); both match the kind of error that a plan or compile
check cannot see.

## Illustrative scenarios (not fitted to the case)

Base scenario: `R = 0.78`, `G = 0.60`, `d_g = 0.45`, `d_r = 0.60`, `c = 0.50`, `k = 2`, `r = 0.30`.
`R` is near the table recall of the full configuration; every other value is chosen for contrast.

| Quantity | Value |
|---|---|
| No correction | 0.4680 |
| Ceiling `1 - U` with a return to retrieval | 0.7404 |
| Ceiling of the linear pipeline (`r = 0`) | 0.6084 |
| Semantic fixer (`c = 0.50`, `e = 0.05`), `k = 2` | 0.6054 |
| Compile-only fixer (`c = 0.03`, `e = 0.90`), `k = 2` | 0.4738 |
| Silent error, compile-only fixer, `k = 0` -> `k = 2` | 0.2596 -> 0.5244 |
| With false positives (`f = 0.10`, `b = 0.50`), best `k` | 0 |

These show the shape of the effect (a compile-only fixer converges quickly to a low plateau and
doubles the silent error; a semantic fixer approaches the ceiling), not the parameters of any real
system.

## Limits

- Independence across stages and across rounds is assumed.
- `d_g`, `d_r`, `c`, `e` are properties of a validator-corrector pair on a question distribution;
  the model does not estimate them. Estimating them needs labelled error data the case does not
  publish.
- The evidence is a single table, one run, one judge, without intervals.
- The ceiling is a statement about the detection coverage of a deterministic validator. A validator
  that checks semantics (for example a value-aware or result-aware check) changes `d_g`, `d_r` and
  therefore `U`.
