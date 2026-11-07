#!/usr/bin/env python3
"""Run the whole pipeline: results -> figures -> tests -> provenance.

Modes
-----
``python3 run_all.py`` (no flag): regenerates ``results.json`` and the figures (Portuguese and
    English) into ``output/replicated/`` (never into a sealed path) and compares ``results.json``
    BYTE FOR BYTE with the sealed one under ``output/``. The figures are compared too, but a
    difference only warns: rendered images depend on the font rasteriser. Then the test suite
    runs and the provenance chain is verified. Exit 0 only if every step passes. If a sealed
    output is missing, the run names it and stops before regenerating anything.
``python3 run_all.py --publish``: the same run written to the SEALED paths (``output/results.json``
    and ``output/figures/``), followed by the tests, the seal (``make_provenance.py``) and the
    verification. The seal is written only if every step and the tests passed; otherwise it is
    skipped and counted as a failure. It is the only mode that writes a sealed path.

The write targets of the default mode are disjoint from every sealed glob of
``configs/stages.json``; ``tests/test_stages_disjoint.py`` asserts it.
"""

from __future__ import annotations

import argparse
import filecmp
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable
OUTPUT = ROOT / "output"
# Child processes write no bytecode: a ``__pycache__`` inside the tree would carry the absolute
# path of the machine that ran it (``.gitignore`` excludes it; this keeps the tree clean).
ENV = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
REPLICATED_DIR = "output/replicated"

LANGUAGES = ("pt", "en")
FIGURES = ("fig_anatomy", "fig_ablation", "fig_ceiling", "fig_architecture")
# compared byte for byte (paths relative to a base dir)
COMPARED = ("results.json",)
# rendered images depend on the font rasteriser: compared, but a difference only warns
IMAGES = tuple(
    f"figures/{fig}_{lang}.{ext}" for fig in FIGURES for lang in LANGUAGES for ext in ("png", "svg")
)


def targets(base: str) -> list[str]:
    """Return every file (relative to the repository root) that a run into ``base`` writes."""
    return [f"{base}/{rel}" for rel in (*COMPARED, *IMAGES)]


def _run(step: str, cmd: list[str]) -> int:
    """Run one step as a subprocess from the repository root; print its duration; return exit."""
    t0 = time.perf_counter()
    rc = subprocess.run(cmd, cwd=ROOT, env=ENV).returncode
    print(f"[{'OK' if rc == 0 else 'FAIL'}] {step} ({time.perf_counter() - t0:.0f} s)", flush=True)
    return rc


def generate(base: Path) -> int:
    """Regenerate ``results.json`` and the figures into ``base``; return the failed steps."""
    steps = [("results", [PY, "code/analysis.py", "--out", str(base)])]
    for lang in LANGUAGES:
        steps.append(
            (
                f"figures ({lang})",
                [
                    PY,
                    "scripts/make_figures.py",
                    "--results",
                    str(base / "results.json"),
                    "--out",
                    str(base / "figures"),
                    "--lang",
                    lang,
                ],
            )
        )
    return sum(_run(name, cmd) != 0 for name, cmd in steps)


def missing_sealed() -> list[str]:
    """Return the sealed outputs (relative to ``output/``) that are not files on disk."""
    return [rel for rel in (*COMPARED, *IMAGES) if not (OUTPUT / rel).is_file()]


def compare(base: Path) -> int:
    """Compare the regenerated outputs in ``base`` with the sealed ones; return mismatches.

    A file missing on either side is a failure with its name, images included (a missing image is
    not a rasterizer difference).
    """
    failures = 0
    for rel in (*COMPARED, *IMAGES):
        missing = [
            side
            for side, root in (("regenerated", base), ("sealed", OUTPUT))
            if not (root / rel).is_file()
        ]
        if missing:
            failures += 1
            print(f"[MISSING] {rel} ({' and '.join(missing)} output absent)")
            continue
        same = filecmp.cmp(base / rel, OUTPUT / rel, shallow=False)
        if rel in IMAGES:
            print(f"[{'SAME' if same else 'WARN'}] {rel}" + ("" if same else " (image differs)"))
        else:
            failures += not same
            print(f"[{'SAME' if same else 'DIFF'}] {rel}")
    return failures


def main(argv=None) -> int:
    """Run the selected mode; return the number of failed steps (0 = all green)."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--publish", action="store_true", help="run into the sealed paths and seal")
    args = ap.parse_args(argv)

    tests = [PY, "-m", "pytest", "-q", "--color=no", "-p", "no:cacheprovider"]
    verify = [PY, "make_provenance.py", "--verify"]
    if args.publish:
        failures = generate(OUTPUT)
    else:
        absent = missing_sealed()
        for rel in absent:
            print(f"[MISSING] output/{rel} (sealed output absent: nothing to compare against)")
        if absent:
            print(f"run_all: {len(absent)} failure(s), stopped before regenerating anything")
            return len(absent)
        failures = generate(ROOT / REPLICATED_DIR)
        failures += compare(ROOT / REPLICATED_DIR)
    failures += _run("tests", tests) != 0
    if args.publish:  # the tests run BEFORE the seal: a failing run is never sealed
        if failures:
            print(f"[FAIL] seal skipped: {failures} failure(s) before it")
            failures += 1
        else:
            failures += _run("seal", [PY, "make_provenance.py"]) != 0
    failures += _run("provenance verify", verify) != 0
    print(f"run_all: {'GREEN' if failures == 0 else f'{failures} failure(s)'}")
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
