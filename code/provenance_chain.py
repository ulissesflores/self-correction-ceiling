"""Staged provenance chain: a Merkle hash chain over a scientific run.

Vendored verbatim (standard library only) from the author's house tooling; only comments and
docstrings that pointed to private material were reworded. A single
ROOT seals (environment -> code -> prereg -> generation -> scores -> figures -> paper)
into one SHA-256 value such that one altered byte anywhere changes ROOT. Pure stdlib
(hashlib/json/pathlib) — no third-party dependency, offline-verifiable by any third party.

Mechanism
---------
* Each STAGE hashes to 32 raw bytes: either a single file's SHA-256 (kind "file"), or an
  RFC 6962 Merkle Tree Hash (MTH) over a set of (relpath, filehash) entries (kind "tree").
* Stages are folded in a FIXED scientific order into ROOT via a domain-separated linear
  hash-link (Haber & Stornetta 1991):  acc = SHA-256(0x02 || acc || stage_i).
* Domain-separation bytes are non-negotiable — 0x00 leaf, 0x01 interior (RFC 6962),
  0x02 chain-link — they block leaf/interior/link second-preimage confusion.
* Every file hash is over LITERAL bytes on disk, never re-serialized JSON: verification is
  byte-identical across machines (avoids the JSON key-order / float-format footgun).
* ROOT goes INTO manifest.json; the manifest is the roof, never a Merkle leaf (no cycle).
  Inter-run: manifest carries prev_chain_head; runs/CHAIN.jsonl links heads append-only.
  Release seals the head via signed git tag + Zenodo VERSION DOI (external time anchor).

What it PROVES (given the published head): internal integrity of every artifact, the
declared stage order, and binding of (env+code+inputs) to (outputs). What it does NOT
prove without add-ons: wall-clock time / non-backdating (needs the external anchor;
trustless upgrade = OpenTimestamps), bit-identical re-execution (needs same-arch +
pinned BLAS + single-thread; else tolerance-reproducible), or scientific correctness.

Prior art (assembled, not invented): Merkle (1987, CRYPTO '87); Haber & Stornetta (1991,
J. Cryptology 3(2)); RFC 6962 (Certificate Transparency: MTH + 0x00/0x01 domain sep);
git object model. Cite these; claim only the assembly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

LEAF = b"\x00"  # RFC 6962 leaf domain
NODE = b"\x01"  # RFC 6962 interior domain
LINK = b"\x02"  # chain-link domain (Haber-Stornetta fold)

ZERO_HEX = "0" * 64


# --------------------------------------------------------------------------- #
# primitives                                                                  #
# --------------------------------------------------------------------------- #
def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    """Streamed SHA-256 hex of a file's literal bytes."""
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def _mth(entries: list[bytes]) -> bytes:
    """RFC 6962 Merkle Tree Hash over raw entry byte-strings -> 32 raw bytes.

    MTH({})    = SHA-256()
    MTH({d0})  = SHA-256(0x00 || d0)
    MTH(D[:n]) = SHA-256(0x01 || MTH(D[:k]) || MTH(D[k:])),  k = largest 2^x < n
    """
    n = len(entries)
    if n == 0:
        return hashlib.sha256(b"").digest()
    if n == 1:
        return hashlib.sha256(LEAF + entries[0]).digest()
    k = 1
    while k < n:  # largest power of two STRICTLY less than n
        k <<= 1
    k >>= 1
    return hashlib.sha256(NODE + _mth(entries[:k]) + _mth(entries[k:])).digest()


def _entry(relpath: str, filehash_hex: str) -> bytes:
    """Canonical Merkle entry: relpath || 0x00 || raw-32-byte-filehash."""
    return relpath.encode("utf-8") + b"\x00" + bytes.fromhex(filehash_hex)


def tree_hash(files: list[tuple[str, str]]) -> bytes:
    """Merkle root (32 raw bytes) over (relpath, filehash) pairs, sorted by relpath."""
    entries = [_entry(rp, fh) for rp, fh in sorted(files, key=lambda x: x[0])]
    return _mth(entries)


def fold(stage_hashes: list[bytes]) -> str:
    """Fold ordered 32-byte stage hashes into ROOT via domain-separated hash-link."""
    if not stage_hashes:
        raise ValueError("no stages to fold")
    acc = stage_hashes[0]
    for s in stage_hashes[1:]:
        acc = hashlib.sha256(LINK + acc + s).digest()
    return acc.hex()


def link_head(prev_chain_head: str, root_hex: str) -> str:
    """Inter-run append link. Genesis (empty prev) -> chain_head == root."""
    if not prev_chain_head or prev_chain_head == ZERO_HEX:
        return root_hex
    return hashlib.sha256(
        LINK + bytes.fromhex(prev_chain_head) + bytes.fromhex(root_hex)
    ).hexdigest()


# --------------------------------------------------------------------------- #
# stage resolution + build                                                    #
# --------------------------------------------------------------------------- #
def _resolve(root: Path, globs: list[str]) -> list[Path]:
    """Return the distinct files matched by ``globs`` under ``root``, in glob then path order."""
    seen: set[Path] = set()
    uniq: list[Path] = []
    for g in globs:
        for p in sorted(root.glob(g)):
            if p.is_file() and p not in seen:
                seen.add(p)
                uniq.append(p)
    return uniq


def stage_hash(root: Path, stage: dict) -> tuple[bytes, list[dict]]:
    """Return (32-byte stage hash, sorted list of {path, sha256, size} leaves).

    `size` is metadata only (DVC records it beside every hash to flag a truncated/
    swapped file before any recompute); it is NOT a Merkle input, so it never affects
    the stage hash or ROOT.
    """
    kind = stage["kind"]
    if kind == "file":
        rel = stage["path"]
        digest = sha256_file(root / rel)
        leaf = {"path": rel, "sha256": digest, "size": (root / rel).stat().st_size}
        return bytes.fromhex(digest), [leaf]
    if kind == "tree":
        files = _resolve(root, stage["globs"])
        if not files and stage.get("required", True):
            raise FileNotFoundError(f"stage {stage['name']!r}: no files matched {stage['globs']}")
        pairs = sorted((str(p.relative_to(root)), sha256_file(p)) for p in files)
        leaves = [
            {"path": rp, "sha256": fh, "size": (root / rp).stat().st_size} for rp, fh in pairs
        ]
        return tree_hash(pairs), leaves
    raise ValueError(f"unknown stage kind: {kind!r}")


def build_chain(root: Path, stages_cfg: dict, prev_chain_head: str = "") -> dict:
    """Compute the full provenance object for one run from files on disk."""
    if stages_cfg.get("hash_alg", "sha256") != "sha256":
        raise ValueError("only sha256 is supported")
    computed: list[dict] = []
    stage_hashes: list[bytes] = []
    for st in stages_cfg["stages"]:
        h, leaves = stage_hash(root, st)
        stage_hashes.append(h)
        computed.append(
            {
                "name": st["name"],
                "kind": st["kind"],
                "nfiles": len(leaves),
                "hash": h.hex(),
                "leaves": leaves,
            }
        )
    root_hex = fold(stage_hashes)
    return {
        "hash_alg": "sha256",
        "domain_separation": {"leaf": "0x00", "node": "0x01", "link": "0x02"},
        "stage_order": [st["name"] for st in stages_cfg["stages"]],
        "stages": computed,
        "prev_chain_head": prev_chain_head or ZERO_HEX,
        "root": root_hex,
        "chain_head": link_head(prev_chain_head, root_hex),
    }


# --------------------------------------------------------------------------- #
# verify                                                                       #
# --------------------------------------------------------------------------- #
def verify(root: Path, stages_path: Path, provenance: dict, expect: str | None = None) -> list[str]:
    """Recompute the chain from disk and return a list of human-readable mismatches.

    An empty list means verified. `provenance` is the sealed object from manifest.json.
    """
    stages_cfg = json.loads(Path(stages_path).read_text(encoding="utf-8"))
    prev = provenance.get("prev_chain_head", "")
    recomputed = build_chain(root, stages_cfg, "" if prev == ZERO_HEX else prev)
    problems: list[str] = []

    claimed_stages = {s["name"]: s for s in provenance.get("stages", [])}
    for s in recomputed["stages"]:
        c = claimed_stages.get(s["name"])
        if c is None:
            problems.append(f"stage {s['name']}: present on disk, absent in manifest")
        elif c["hash"] != s["hash"]:
            problems.append(
                f"stage {s['name']}: hash mismatch "
                f"(manifest {c['hash'][:12]}… != disk {s['hash'][:12]}…)"
            )
    if recomputed["root"] != provenance.get("root"):
        problems.append(
            f"ROOT mismatch (manifest {str(provenance.get('root'))[:12]}… "
            f"!= disk {recomputed['root'][:12]}…)"
        )
    if recomputed["chain_head"] != provenance.get("chain_head"):
        problems.append("chain_head mismatch")
    if expect and recomputed["chain_head"] != expect:
        problems.append(f"chain_head != --expect ({expect[:12]}…)")
    return problems


# --------------------------------------------------------------------------- #
# venue-legibility helpers (wrap the SAME leaves in formats reviewers know)    #
# --------------------------------------------------------------------------- #
_DOI_RE = None  # lazy-compiled below


def valid_version_doi(doi: str) -> bool:
    """Return True iff `doi` is a full, untruncated Zenodo VERSION DOI (10.5281/zenodo.<n>).

    Guards against a truncated identifier (zenodo.207699 != zenodo.20769940). The concept
    DOI is intentionally the same pattern; the version-vs-concept rule is enforced elsewhere
    (the citation policy of the paper) — this only rejects a malformed/truncated string.
    """
    global _DOI_RE
    if _DOI_RE is None:
        import re

        _DOI_RE = re.compile(r"^10\.5281/zenodo\.\d{5,}$")
    return bool(_DOI_RE.match(doi.strip()))


def write_sha256sums(provenance: dict, out_path: Path) -> int:
    """Emit sha256sums.txt over every leaf and return the file count.

    A third party can `sha256sum -c` it with zero knowledge of this tool (CWLProv/BagIt-style
    fixity).
    """
    seen: dict[str, str] = {}
    for st in provenance["stages"]:
        for lf in st["leaves"]:
            seen[lf["path"]] = lf["sha256"]
    lines = [f"{h}  {p}" for p, h in sorted(seen.items())]
    Path(out_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(seen)


# --------------------------------------------------------------------------- #
# self-test (executable proof: any tampered byte flips ROOT)                   #
# --------------------------------------------------------------------------- #
def _selftest() -> int:
    """Run the executable self-test (known answers, tamper detection, linkage); return 0."""
    import tempfile

    # 1) RFC 6962 known-answer: empty tree == SHA-256("")
    empty = _mth([]).hex()
    assert empty == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", empty
    # single-leaf == SHA-256(0x00 || d0)
    d0 = b"leaf-data"
    assert _mth([d0]).hex() == hashlib.sha256(LEAF + d0).hexdigest()
    # domain separation actually separates leaf vs node
    assert (
        _mth([b"a", b"b"])
        != hashlib.sha256(
            hashlib.sha256(LEAF + b"a").digest() + hashlib.sha256(LEAF + b"b").digest()
        ).digest()
    )

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "code").mkdir()
        (root / "output").mkdir()
        (root / "code" / "a.py").write_text("print('hello')\n")
        (root / "code" / "b.py").write_text("x = 1\n")
        (root / "PREREG.md").write_text("H1: retrieval does not pay.\n")
        (root / "output" / "scores.json").write_text('{"mi_bits": 0.0004}\n')
        cfg = {
            "hash_alg": "sha256",
            "stages": [
                {"name": "prereg", "kind": "file", "path": "PREREG.md"},
                {"name": "code", "kind": "tree", "globs": ["code/*.py"]},
                {"name": "scores", "kind": "file", "path": "output/scores.json"},
            ],
        }
        stages_path = root / "stages.json"
        stages_path.write_text(json.dumps(cfg))

        prov = build_chain(root, cfg)
        root0 = prov["root"]
        assert prov["chain_head"] == root0  # genesis: head == root
        assert not verify(root, stages_path, prov), "clean run must verify"

        # tamper each stage in turn: ROOT must change AND verify must catch it
        for target, mutate in [
            ("PREREG.md", "H1: retrieval PAYS (moved goalpost).\n"),  # prereg
            ("code/a.py", "print('hi')\n"),  # code
            ("output/scores.json", '{"mi_bits": 0.9}\n'),  # scores
        ]:
            original = (root / target).read_text()
            (root / target).write_text(mutate)
            tampered = build_chain(root, cfg)
            assert tampered["root"] != root0, f"tamper of {target} did NOT change ROOT"
            assert verify(root, stages_path, prov), f"verify missed tamper of {target}"
            (root / target).write_text(original)  # restore
        assert not verify(root, stages_path, prov), "restore must re-verify"

        # inter-run linkage: run 2 links run 1's head; reordering breaks it
        prov2 = build_chain(root, cfg, prev_chain_head=root0)
        assert prov2["chain_head"] != prov2["root"], "linked run head must fold prev"
        assert prov2["chain_head"] == link_head(root0, prov2["root"])

        # venue-legibility: leaves carry size; sha256sums round-trips under `sha256sum -c`
        assert all("size" in lf for s in prov["stages"] for lf in s["leaves"])
        n = write_sha256sums(prov, root / "sha256sums.txt")
        sums = (root / "sha256sums.txt").read_text().splitlines()
        assert n == len(sums) == 4  # 2 code + prereg + scores
        for line in sums:
            digest, rel = line.split("  ", 1)
            assert sha256_file(root / rel) == digest, f"sha256sums drift on {rel}"

    # DOI truncation guard: full passes, truncated fails
    assert valid_version_doi("10.5281/zenodo.20769940")
    assert not valid_version_doi("10.5281/zenodo.2076")
    assert not valid_version_doi("zenodo.20769940")

    print(
        "[OK] provenance_chain self-test passed "
        "(RFC 6962 KAT + tamper-detection + linkage + sha256sums + DOI guard)"
    )
    return 0


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    """Command-line entry point: ``build``, ``verify`` or ``selftest``."""
    ap = argparse.ArgumentParser(description="Staged provenance chain.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="compute the provenance object and print JSON")
    b.add_argument("root", type=Path)
    b.add_argument("--stages", type=Path, required=True)
    b.add_argument("--prev", default="", help="previous run chain_head (empty for genesis)")

    v = sub.add_parser("verify", help="recompute from disk against a sealed manifest")
    v.add_argument("root", type=Path)
    v.add_argument("--stages", type=Path, required=True)
    v.add_argument(
        "--manifest",
        type=Path,
        required=True,
        help="manifest.json holding provenance under key 'provenance'",
    )
    v.add_argument("--expect", default=None, help="assert chain_head equals this hex")

    sub.add_parser("selftest", help="run the executable tamper-detection proof")

    args = ap.parse_args(argv)
    if args.cmd == "selftest":
        return _selftest()
    if args.cmd == "build":
        obj = build_chain(args.root, json.loads(args.stages.read_text(encoding="utf-8")), args.prev)
        print(json.dumps(obj, indent=2))
        return 0
    if args.cmd == "verify":
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        prov = manifest.get("provenance", manifest)
        problems = verify(args.root, args.stages, prov, args.expect)
        if problems:
            for p in problems:
                print(f"[FAIL] {p}")
            print(f"[FAIL] {len(problems)} mismatch(es) — chain is BROKEN")
            return len(problems)
        print(f"[OK] chain verified — chain_head {prov.get('chain_head')}")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
