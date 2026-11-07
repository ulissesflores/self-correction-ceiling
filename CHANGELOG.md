# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project follows
[Semantic Versioning](https://semver.org/). Versions below 1.0.0 are pre-release.

## [0.1.0] - 2026-11-07

### Archived

- Zenodo concept DOI [10.5281/zenodo.24041990](https://doi.org/10.5281/zenodo.24041990); the `0.1.0-rc1` archive has the version DOI
  [10.5281/zenodo.24041991](https://doi.org/10.5281/zenodo.24041991).

### Added

- Closed-form accuracy of a `retrieve -> generate -> validate -> correct` pipeline
  (`code/ceiling.py`) with the ceiling `1 - U` and its corollaries (`docs/THEORY.md`).
- Event-level Monte Carlo used as a known-answer test of the closed form (`code/simulate.py`),
  and the heterogeneity identity check.
- Arithmetic of Table 2 of Chen et al. (2025, arXiv:2507.14372) and of Sections 3.3.4 and 4
  (`data/linkedin_ablation.json`, `code/analysis.py`, `output/results.json`).
- Identified range of the silent error from the published totals, `max(0, C - Q) <= S <=
  min(C, 100 - Q)` (29-53% without the query fixer, 48-53% with it), and the descriptive
  correlations across the 13 ablation configurations (compile 0.27, table recall 0.91).
- Four figures in Portuguese and English, PNG and SVG (`scripts/make_figures.py`): the intuition
  of the ceiling, the ablation with the identified ranges, the model by correction rounds and the
  write-query flow of the case.
- Tests that lock every published number, the model laws, the known-answer test and the
  disjointness of replication and sealed paths.
- SHA-256 provenance chain (`make_provenance.py`, `code/provenance_chain.py`,
  `configs/stages.json`, `runs/`), `run_all.py`, CI, dual license, citation metadata.
