# Roadmap

Honest next steps; none is done.

## 0.1.1 (current)

The submitted paper in `docs/paper/`; nothing else changes.

## 0.1.0

Model, proofs, known-answer test, arithmetic of one public table, four figures, sealed chain.
Public on GitHub and archived on Zenodo (concept DOI 10.5281/zenodo.24041990).

## Before the first citable version

- ~~Verify the transcription of `data/linkedin_ablation.json` a second time, independently of the
  first reading.~~ Done 2026-11-07: a second, independent reading matched all 104 values (13
  configurations x 8 metrics) against the preprint table.
- ~~Decide, with the author, when the repository goes public; the DOI is minted by the first release,
  not before.~~ Done 2026-11-07: public, `0.1.0-rc1` archived on Zenodo.

## 0.2.0 (candidates)

- **Estimation, not only illustration.** A procedure to estimate `d_g`, `d_r`, `c`, `e` from
  labelled correction traces, with intervals, and a public dataset (or a synthetic one with a
  known truth) on which it is validated. Without this, the scenarios stay illustrative.
- **Validator variants.** Extend `d` to value-aware and result-aware checks and quantify how much
  `U` shrinks.
- **Dependence between rounds.** Relax the independence assumption (a corrector that fails once is
  more likely to fail again) and bound the error it introduces.
- **A replication notebook** (`colab/`) that verifies its own hashes with zero setup.
- **More public ablations.** Apply the same arithmetic to other published text-to-SQL ablations that
  report both an executability and a correctness metric, with the same caveats.
