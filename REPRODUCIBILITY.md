# Reproducibility

This repository follows a two-seals contract: what is **derived** can be regenerated and is
compared byte for byte; what is **frozen evidence** was read from a public document once and can
only be checked against its own hash, not regenerated.

## The two seals

| Seal | What it covers | How it is checked |
|---|---|---|
| Derivation (reproducible) | `output/results.json` from `data/linkedin_ablation.json` and the code; the Monte Carlo with fixed seeds | `python run_all.py` regenerates into `output/replicated/` and compares `results.json` byte for byte |
| Frozen evidence (not re-runnable) | `data/linkedin_ablation.json`: integers copied from Table 2 and from Sections 3.3.4 and 4 of Chen et al. (2025), arXiv:2507.14372, with the SHA-256 of the PDF that was read | `make_provenance.py --verify` proves the file was not altered; it does not prove that the transcription is right |
| Figures | `output/figures/*` | compared by `run_all.py` but a difference only warns: rendered images depend on the font rasteriser |

## Track 1 (light) and Track 2 (complete)

- **Track 1, about one second of computation plus the tests:**

  ```bash
  python -m pip install -r requirements.txt
  python make_provenance.py --verify
  python run_all.py
  ```

- **Track 2, exact environment of the sealed run.** `requirements.lock` is the verbatim freeze of
  the environment that produced `output/` (CPython 3.13.9); `env.json` is the genesis of the chain.
  Use it to reproduce the figures bit for bit.

`python run_all.py --publish` writes the sealed paths and re-seals; it is the only mode that does,
and it seals only if the regeneration and the tests passed.

## The provenance chain

`configs/stages.json` declares the stages in a fixed order:

```text
environment -> code -> data -> scores -> figures
```

Each stage hashes to 32 bytes (the SHA-256 of one file, or an RFC 6962 Merkle tree over a set of
files); the stages fold into one root with a domain-separated hash link; the root and the head of
the chain are written to `runs/v0.1.0/manifest.json`, and `runs/CHAIN.jsonl` links runs append-only.
`python make_provenance.py --verify` recomputes everything from the files on disk and exits with the
number of problems found.

What the chain **proves**: the internal integrity of every sealed file, the declared order, and the
binding of (environment + code + data) to (scores + figures). What it does **not** prove:
wall-clock time (a release tag or a DOI is the external anchor), bit-identical re-execution on
another platform, or scientific correctness. There is no pre-registration stage: the repository
ships a model, a simulation of it and the arithmetic of a published table.

## What cannot be re-run

- The numbers of the case study. They are transcribed from a document owned by others; the
  repository neither redistributes nor re-measures them.
- Anything about the real system: the model parameters in the scenarios are illustrative.

## Determinism

The Monte Carlo uses fixed seeds (20251109 and 20251110) and `numpy.random.default_rng`.
`results.json` rounds every float, which is meant to keep it stable across platforms; CI is configured to run the
byte comparison on Python 3.11, 3.12 and 3.13. If a future numpy changes the bit-generator stream,
the comparison fails loudly and the fix is a deliberate `--publish`, never an edit of a sealed file.

## Continuous integration

`.github/workflows/ci.yml` configures a `verify` job (matrix Python 3.11, 3.12, 3.13) that runs
`make_provenance.py --verify` and `run_all.py`, and a `lint` job that runs `ruff format --check`,
`ruff check` and `interrogate` (100% docstring coverage).
