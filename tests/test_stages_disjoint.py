"""Replication never writes a sealed path (invariant of the provenance chain).

``run_all.py`` regenerates every output into ``output/replicated/``. If any of its write targets
matched a glob of ``configs/stages.json``, a legitimate replication would silently overwrite
sealed evidence and the next verification would report tampering. The match uses ``Path.glob``
semantics: ``*`` never crosses ``/``. Write targets and their base directories are normalized
first (``posixpath.normpath``) and a ``..`` segment is refused outright:
``output/replicated/../figures`` would otherwise escape the segment-wise match while the run
writes into ``output/figures``.
"""

import fnmatch
import importlib.util
import json
import posixpath
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run_all():
    """Import ``run_all.py`` from the repository root as a module."""
    spec = importlib.util.spec_from_file_location("run_all", ROOT / "run_all.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sealed() -> list[str]:
    """Return every sealed path or glob of ``configs/stages.json``."""
    cfg = json.loads((ROOT / "configs" / "stages.json").read_text(encoding="utf-8"))
    patterns = []
    for stage in cfg["stages"]:
        patterns += [stage["path"]] if stage["kind"] == "file" else stage["globs"]
    return patterns


def _normal(path: str) -> str:
    """Return ``path`` normalized; fail if it has a ``..`` segment or leaves the repository."""
    assert ".." not in path.split("/"), f"write path climbs with '..': {path}"
    normal = posixpath.normpath(path)
    assert not posixpath.isabs(normal), f"write path is absolute: {path}"
    return normal


def _matches(path: str, pattern: str) -> bool:
    """Match like ``Path.glob``: same number of segments, ``fnmatch`` segment by segment."""
    parts, globs = path.split("/"), pattern.split("/")
    return len(parts) == len(globs) and all(
        fnmatch.fnmatchcase(p, g) for p, g in zip(parts, globs, strict=True)
    )


def test_sealed_globs_without_recursion():
    """Check that no sealed glob uses ``**`` (the segment-wise match below would not cover it)."""
    assert not any("**" in g for g in _sealed())


def test_replication_targets_disjoint_from_sealed():
    """Check that no file written by the replicated run matches a sealed glob."""
    ra = _run_all()
    sealed = _sealed()
    for base in (ra.REPLICATED_DIR,):
        base_normal = _normal(base)
        for target in ra.targets(base):
            collisions = [g for g in sealed if _matches(_normal(target), g)]
            assert collisions == [], (target, collisions)
        assert not any(g.startswith(base_normal + "/") for g in sealed), base


def test_publish_writes_only_sealed_paths():
    """Check that every output of ``--publish`` is covered by a sealed glob (nothing unsealed)."""
    ra = _run_all()
    sealed = _sealed()
    for target in ra.targets("output"):
        assert any(_matches(_normal(target), g) for g in sealed), target
