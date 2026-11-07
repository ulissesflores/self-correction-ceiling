#!/usr/bin/env python3
"""Freeze the execution environment into ``env.json``, the genesis of the provenance chain.

The ``environment`` stage is the first link of ``configs/stages.json``: its hash is the hash of the
LITERAL BYTES of ``env.json`` on disk, never of the live environment. That is what lets the ROOT
recompute byte-identically on any machine, months later.

Hard rule: if ``env.json`` already exists it is NOT overwritten (exit 0 with a notice). Rewriting
the genesis silently changes the ROOT and invalidates every sealed manifest. Re-sealing is a
deliberate act: ``--reseal``.
"""

from __future__ import annotations

import argparse
import json
import platform
import struct
import sys
from datetime import UTC, datetime
from pathlib import Path

# Repository root = parent of code/. Deriving it from __file__ (not from the working directory)
# lets the tests run this script on a temporary copy of the repository.
ROOT = Path(__file__).resolve().parent.parent

# Third-party libraries actually imported by code/, scripts/ and tests/. When a real dependency is
# added, append its distribution name here and re-seal with --reseal.
LIBRARIES_USED: list[str] = ["numpy", "matplotlib", "pytest"]


def _versions(names: list[str]) -> dict[str, str]:
    """Return the installed version of each distribution (``MISSING`` if absent)."""
    from importlib.metadata import PackageNotFoundError, version

    out: dict[str, str] = {}
    for name in names:
        try:
            out[name] = version(name)
        except PackageNotFoundError:
            out[name] = "MISSING"
    return out


def snapshot() -> dict:
    """Return a portrait of the environment.

    No absolute paths: they are not reproducible on another machine and would leak the local tree
    into a sealed artifact.
    """
    return {
        "_nature": "generated",
        "_role": "genesis of the provenance chain (stage `environment`)",
        "frozen_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "compiler": platform.python_compiler(),
            "full_version": sys.version.replace("\n", " "),
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "description": platform.platform(),
        },
        "architecture": {
            "machine": platform.machine(),
            "processor": platform.processor(),
            "pointer_bits": struct.calcsize("P") * 8,
            "byte_order": sys.byteorder,
        },
        "libraries": _versions(LIBRARIES_USED),
        "_note_libraries": "Third-party libraries actually imported by code/, scripts/ and tests/.",
    }


def main(argv: list[str] | None = None) -> int:
    """Write ``env.json`` unless it exists (or ``--reseal`` is given); return 0."""
    ap = argparse.ArgumentParser(description="Freeze env.json (genesis of the chain).")
    ap.add_argument(
        "--root", type=Path, default=ROOT, help="repository root (default: parent of code/)"
    )
    ap.add_argument(
        "--reseal",
        action="store_true",
        help="overwrite env.json on purpose: changes the ROOT of the whole chain",
    )
    args = ap.parse_args(argv)

    dest_path = Path(args.root) / "env.json"
    if dest_path.exists() and not args.reseal:
        print(
            f"[SKIP] {dest_path.name} already exists: genesis preserved. "
            f"Use --reseal to overwrite it on purpose (this changes the ROOT)."
        )
        return 0

    dest_path.write_text(
        json.dumps(snapshot(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"[OK] {'resealed' if args.reseal else 'frozen'}: {dest_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
