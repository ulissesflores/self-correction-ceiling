#!/usr/bin/env python3
"""Build or verify the provenance chain of this repository.

``python3 make_provenance.py`` (build): freezes ``env.json`` if it is absent (genesis), hashes
every stage of ``configs/stages.json`` (environment -> code -> prereg -> data -> scores ->
figures) with the vendored ``code/provenance_chain.py`` and writes the seal:

- ``runs/<RUN_ID>/manifest.json``: the provenance object (stage hashes, leaves, ROOT, chain head);
  every path in it is relative to the repository root;
- ``runs/<RUN_ID>/sha256sums.txt``: one line per sealed file, checkable with ``sha256sum -c``;
- ``runs/CHAIN.jsonl``: one line per run (``run_id``, ``prev_chain_head``, ``root``,
  ``chain_head``).

``python3 make_provenance.py --verify``: recomputes the chain from the files on disk and compares
it with the sealed manifest: every stage hash, the ROOT and the chain head, and also every leaf the
manifest lists (path, SHA-256 and size, stage by stage) and ``sha256sums.txt``, regenerated from
the manifest and compared byte for byte. It checks that the manifest holds no absolute path and
walks ``runs/CHAIN.jsonl`` line by line: the first line links to the zero head, each
``prev_chain_head`` is the ``chain_head`` of the line before, each ``chain_head`` is the link of
its ``prev_chain_head`` and ``root``, and the line of this run equals the manifest. Exit code =
number of problems, at most 255 (an exit status is taken modulo 256; 0 = verified).

The manifest, ``configs/stages.json`` and ``runs/CHAIN.jsonl`` are read first. Each one that is
missing, unreadable, not valid JSON, or not the structure the build writes (the manifest, the
chain file) or reads (the stages file) is one problem that names it, and nothing is recomputed:
a key missing, or extra in the manifest or a chain line, a value of another JSON type, a stage
path that is not relative to the root. A sealed file that is missing or unreadable is named by
its path relative to the root; a missing file of a tree stage also changes the hash of its stage,
the root and the chain head, and each of these is reported. No failure of ``--verify`` ends in a
traceback or with exit code 0.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "code"))

import freeze_env  # noqa: E402
import provenance_chain as pc  # noqa: E402

RUN_ID = "v0.1.0"
STAGES = ROOT / "configs" / "stages.json"
RUNS = ROOT / "runs"
MANIFEST = RUNS / RUN_ID / "manifest.json"
CHAIN = RUNS / "CHAIN.jsonl"
CHAIN_FIELDS = ("chain_head", "prev_chain_head", "root", "run_id")

# The structure the build writes, which --verify checks before it recomputes anything: a dict lists
# the keys, a one-item list gives the form of every item, a type is the exact JSON type.
MANIFEST_SHAPE = {
    "hash_alg": str,
    "domain_separation": {"leaf": str, "node": str, "link": str},
    "stage_order": [str],
    "stages": [
        {
            "name": str,
            "kind": str,
            "nfiles": int,
            "hash": str,
            "leaves": [{"path": str, "sha256": str, "size": int}],
        }
    ],
    "prev_chain_head": str,
    "root": str,
    "chain_head": str,
}
STAGE_SHAPE = {"file": {"name": str, "path": str}, "tree": {"name": str, "globs": [str]}}
JSON_TYPE = {
    dict: "an object",
    list: "an array",
    str: "a string",
    int: "an integer",
    float: "a number",
    bool: "a boolean",
    type(None): "null",
}


def _name(path: Path) -> str:
    """Return ``path`` relative to the repository root, or its bare name if it lies outside."""
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else path.name


def _text(path: Path) -> str:
    """Return the text of ``path``; a file that cannot be read as UTF-8 text is named.

    Raises
    ------
    ValueError
        If the file is missing or unreadable, or its bytes are not UTF-8 text.
    """
    try:
        return path.read_text(encoding="utf-8")
    except OSError as err:
        raise ValueError(f"{_name(path)} cannot be read ({err.strerror or err})") from err
    except UnicodeDecodeError as err:
        raise ValueError(f"{_name(path)} is not valid JSON ({err})") from err


def _json(path: Path, text: str | None = None):
    """Parse ``text`` (default: the whole file ``path``); a parse error names the file.

    Raises
    ------
    ValueError
        If the file cannot be read, or the text is not valid JSON (truncated, or nested too deeply
        for the parser).
    """
    try:
        return json.loads(_text(path) if text is None else text)
    except (json.JSONDecodeError, RecursionError) as err:
        raise ValueError(f"{_name(path)} is not valid JSON ({err})") from err


def _chain() -> list[dict]:
    """Return the lines of ``runs/CHAIN.jsonl`` (empty list if the file does not exist)."""
    if not CHAIN.exists():
        return []
    return [_json(CHAIN, x) for x in _text(CHAIN).splitlines() if x.strip()]


def _relative(path: str) -> bool:
    """Return True if ``path`` is a non-empty path inside the root (not absolute, no ``..``)."""
    return bool(path) and not Path(path).is_absolute() and ".." not in Path(path).parts


def _deviation(obj, shape, where: str = "", exact: bool = False) -> str | None:
    """Return where ``obj`` departs from ``shape``, or None if it has that structure.

    Parameters
    ----------
    obj : object
        A parsed JSON value.
    shape : dict, list or type
        A dict of required keys, a one-item list with the form of every item, or the exact type (a
        JSON boolean is not an integer).
    where : str
        Where ``obj`` sits in the file, for the message (empty at the top level).
    exact : bool
        If True, an object with a key that ``shape`` does not list departs too, at every depth.

    Returns
    -------
    str or None
        The first departure found, e.g. ``"stages[0].leaves[0] has no key 'size'"``.
    """
    expected = type(shape) if isinstance(shape, dict | list) else shape
    if type(obj) is not expected:
        kind_type = (
            f"{JSON_TYPE.get(type(obj), type(obj).__name__)}, expected {JSON_TYPE[expected]}"
        )
        return f"{where} is {kind_type}" if where else kind_type
    if isinstance(shape, dict):
        if exact and set(obj) - set(shape):
            extra = f"extra key(s) {sorted(set(obj) - set(shape))}"
            return f"{where} has {extra}" if where else extra
        for key, sub in shape.items():
            if key not in obj:
                return f"{where} has no key {key!r}" if where else f"no key {key!r}"
            deviation = _deviation(obj[key], sub, f"{where}.{key}" if where else key, exact)
            if deviation:
                return deviation
    if isinstance(shape, list):
        for i, item in enumerate(obj):
            deviation = _deviation(item, shape[0], f"{where}[{i}]", exact)
            if deviation:
                return deviation
    return None


def _stages_deviation(cfg) -> str | None:
    """Return where a stages file departs from what the build reads, or None."""
    deviation = _deviation(cfg, {"stages": [{"kind": str}]})
    if deviation:
        return deviation
    if cfg.get("hash_alg", "sha256") != "sha256":
        return f"hash_alg is {cfg['hash_alg']!r}, expected 'sha256'"
    if not cfg["stages"]:
        return "stages is empty"
    for i, stage in enumerate(cfg["stages"]):
        shape = STAGE_SHAPE.get(stage["kind"])
        if shape is None:
            return f"stages[{i}].kind is {stage['kind']!r}, expected 'file' or 'tree'"
        deviation = _deviation(stage, shape, f"stages[{i}]")
        if deviation:
            return deviation
        for rel in [stage["path"]] if stage["kind"] == "file" else stage["globs"]:
            if not _relative(rel):
                return f"stages[{i}] holds {rel!r}, not a path relative to the repository root"
    return None


def _chain_deviation(lines: list) -> str | None:
    """Return where the lines of the chain file depart from what the build writes, or None."""
    shape = dict.fromkeys(CHAIN_FIELDS, str)
    for i, line in enumerate(lines, start=1):
        deviation = _deviation(line, shape, exact=True)
        if deviation:
            return f"line {i}: {deviation}"
    return None


def _paths(obj) -> list[str]:
    """Return every ``path`` value found anywhere inside a JSON-like object."""
    if isinstance(obj, dict):
        found = [obj["path"]] if isinstance(obj.get("path"), str) else []
        return found + [p for v in obj.values() for p in _paths(v)]
    if isinstance(obj, list):
        return [p for v in obj for p in _paths(v)]
    return []


def build() -> dict:
    """Seal the current files: write manifest, sha256sums and chain line; return the manifest."""
    if not (ROOT / "env.json").exists():
        freeze_env.main(["--root", str(ROOT)])
    previous_lines = [x for x in _chain() if x["run_id"] != RUN_ID]
    prev = previous_lines[-1]["chain_head"] if previous_lines else ""
    stages_cfg = json.loads(STAGES.read_text(encoding="utf-8"))
    prov = pc.build_chain(ROOT, stages_cfg, prev)
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(prov, indent=2) + "\n", encoding="utf-8")
    pc.write_sha256sums(prov, MANIFEST.parent / "sha256sums.txt")
    line = {
        "chain_head": prov["chain_head"],
        "prev_chain_head": prov["prev_chain_head"],
        "root": prov["root"],
        "run_id": RUN_ID,
    }
    CHAIN.write_text(
        "".join(json.dumps(x, sort_keys=True) + "\n" for x in [*previous_lines, line]),
        encoding="utf-8",
    )
    return prov


def _leaves(prov: dict) -> dict[str, list[tuple]]:
    """Return ``{stage: [(path, sha256, size), ...]}`` in manifest order."""
    return {
        s["name"]: [(f["path"], f["sha256"], f["size"]) for f in s["leaves"]]
        for s in prov.get("stages", [])
    }


def _leaf_problems(prov: dict) -> list[str]:
    """Compare every listed leaf and ``sha256sums.txt`` with what the files on disk give."""
    problems = []
    stages_cfg = json.loads(STAGES.read_text(encoding="utf-8"))
    disk = _leaves(pc.build_chain(ROOT, stages_cfg, ""))
    sealed = _leaves(prov)
    for name in sorted(set(disk) | set(sealed)):
        a, b = sealed.get(name, []), disk.get(name, [])
        if a != b:
            manifest_only = sorted(set(a) - set(b))
            disk_only = sorted(set(b) - set(a))
            problems.append(
                f"stage {name}: leaf list differs (manifest only {manifest_only[:3]}, "
                f"disk only {disk_only[:3]})"
            )
    for s in prov.get("stages", []):
        if s.get("nfiles") != len(s["leaves"]):
            problems.append(f"stage {s['name']}: nfiles {s.get('nfiles')} != {len(s['leaves'])}")
    sums = MANIFEST.parent / "sha256sums.txt"
    with tempfile.TemporaryDirectory() as tmp:  # same writer as the build, never re-implemented
        expected = Path(tmp) / "sha256sums.txt"
        pc.write_sha256sums(prov, expected)
        if not sums.exists() or sums.read_bytes() != expected.read_bytes():
            problems.append(f"{sums.relative_to(ROOT)} differs from the manifest")
    return problems


def _chain_problems(prov: dict) -> list[str]:
    """Walk ``runs/CHAIN.jsonl``: genesis, links between lines, and this run's line.

    Each line has already been checked to hold exactly the four string fields the build writes.
    """
    problems = []
    previous = pc.ZERO_HEX
    for i, line in enumerate(_chain(), start=1):
        if line["prev_chain_head"] != previous:
            problems.append(f"runs/CHAIN.jsonl line {i}: prev_chain_head is not the previous head")
        hashes = (line["chain_head"], line["prev_chain_head"], line["root"])
        if not all(isinstance(h, str) and re.fullmatch(r"[0-9a-f]{64}", h) for h in hashes):
            problems.append(f"runs/CHAIN.jsonl line {i}: a hash is not 64 lowercase hex digits")
        elif pc.link_head(line["prev_chain_head"], line["root"]) != line["chain_head"]:
            problems.append(f"runs/CHAIN.jsonl line {i}: chain_head != link(prev, root)")
        previous = line["chain_head"]
    link = [x for x in _chain() if x.get("run_id") == RUN_ID]
    if len(link) != 1:
        problems.append(f"runs/CHAIN.jsonl: {len(link)} lines for {RUN_ID} (expected 1)")
    elif link[0] != {c: (RUN_ID if c == "run_id" else prov.get(c)) for c in CHAIN_FIELDS}:
        problems.append("runs/CHAIN.jsonl: the line of this run differs from the manifest")
    return problems


def _read_for_verify() -> tuple[dict | None, list[str]]:
    """Read the manifest, the stages file and the chain file and check their structure.

    Returns
    -------
    tuple of (dict or None, list of str)
        The parsed manifest, and one problem for each of the three files that is missing,
        unreadable, not valid JSON or not the structure the build writes or reads, naming the file.
    """
    readers = (
        (
            MANIFEST,
            "writes",
            lambda: _json(MANIFEST),
            lambda m: _deviation(m, MANIFEST_SHAPE, exact=True),
        ),
        (STAGES, "reads", lambda: _json(STAGES), _stages_deviation),
        (
            CHAIN,
            "writes",
            lambda: [_json(CHAIN, x) for x in _text(CHAIN).splitlines() if x.strip()],
            _chain_deviation,
        ),
    )
    read_items, problems = {}, []
    for path, verb, read, deviation_of in readers:
        try:
            read_items[path] = read()
        except ValueError as err:
            problems.append(f"cannot verify: {err}")
            continue
        deviation = deviation_of(read_items[path])
        if deviation:
            problems.append(
                f"cannot verify: {_name(path)} is not the structure the build {verb} ({deviation})"
            )
    return read_items.get(MANIFEST), problems


def verify() -> list[str]:
    """Recompute the chain from disk against the sealed manifest; return the problems found."""
    prov, problems = _read_for_verify()
    if problems:  # nothing is recomputed against a file of another structure
        return problems
    problems = pc.verify(ROOT, STAGES, prov)
    for path in _paths(prov):
        if not _relative(path):
            problems.append(f"path in the manifest is not relative to the root: {path}")
    return problems + _leaf_problems(prov) + _chain_problems(prov)


def main(argv=None) -> int:
    """Build the seal, or verify it with ``--verify``; return the problem count (at most 255)."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--verify", action="store_true", help="recompute and compare; exit = problems")
    args = ap.parse_args(argv)
    if args.verify:
        try:
            problems = verify()
        except Exception as err:  # a sealed file that cannot be read, or any other failure:
            # one problem, never a traceback; the message names the file relative to the root,
            # never the machine's absolute path
            detail = str(err).replace(f"{ROOT}/", "")
            problems = [f"cannot verify ({type(err).__name__}): {detail}"]
        for p in problems:
            print(f"[FAIL] {p}")
        if problems:
            print(f"[FAIL] {len(problems)} problem(s): the chain is BROKEN")
        else:
            prov = json.loads(MANIFEST.read_text(encoding="utf-8"))
            print(f"[OK] chain verified: root {prov['root']} · chain_head {prov['chain_head']}")
        return min(len(problems), 255)  # 256 problems would otherwise exit with status 0
    prov = build()
    n = sum(s["nfiles"] for s in prov["stages"])
    print(f"[OK] sealed {n} files in {len(prov['stages'])} stages: root {prov['root']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
