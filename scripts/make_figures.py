#!/usr/bin/env python3
"""Draw the four figures of the companion article from ``output/results.json``.

Claim map ("no figure without a claim"):

- ``fig_anatomy`` (article Figure 2): conceptual. The validator sees syntax and schema errors
  (visible), not a wrong but well-formed filter (silent); a fixer triggered by the validator acts
  only on the visible part, repairing it or silencing it, so the silent part bounds the reachable
  accuracy at ``1 - U``. Proportions and the three queries are illustrative, not data.
- ``fig_ablation`` (article Figure 3): in the published LinkedIn ablation, (a) the query fixer
  raises compilation (76 -> 95) with the share rated 4+ unchanged (47), while the knowledge graph
  moves the rated-4+ share; (b) the share of questions whose query compiles without a 4+ is only
  bounded by the totals, ``[max(0, C - Q), min(C, 100 - Q)]``: 29-53 without the fixer, 48-53
  with it. No assumption that every query rated 4+ compiles.
- ``fig_ceiling`` (repository only): in the closed-form model, a compile-only fixer converges fast
  to a low plateau and doubles the silent error, a semantic fixer approaches the ceiling, and no
  fixer crosses the ceiling ``1 - U``. Illustrative (parameters not fitted to the case).
- ``fig_architecture`` (article Figure 1): the write-query flow of the SQL Bot as documented by
  the case (solid) and the controls the article proposes (dashed), which are proposals, not the
  organization's design.

Usage: ``python3 scripts/make_figures.py --results output/results.json --out output/figures
--lang pt|en``. Writes ``fig_<name>_<lang>.png/.svg`` for the four figures.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "code"))

from ceiling import Params, accuracy, ceiling  # noqa: E402

CORRECT, SILENT, VISIBLE = "#0072B2", "#D55E00", "#7F7F7F"
INK, MUTED, GRID = "#1A1A1A", "#555555", "#DDDDDD"

TXT = {
    "pt": {
        "right_title": "Modelo: acurácia por rodadas de correção (ilustrativo)",
        "cfg": {
            "A.1": "A.1 só esquemas",
            "A.4": "A.4 com exemplos e atributos",
            "B.1": "B.1 sem reordenadores",
            "B.2": "B.2 sem corretor",
            "B.3": "B.3 com corretor",
            "Full": "Completo",
        },
        "rounds": "Rodadas de correção (k)",
        "acc": "Probabilidade",
        "sem_acc": "Acurácia, corretor semântico",
        "cmp_acc": "Acurácia, corretor só de compilação",
        "cmp_sil": "Erro silencioso, corretor só de compilação",
        "ceil": "Teto 1 − U",
        "arch": {
            "q": "Pergunta",
            "intent": "Classificador\nde intenção",
            "fetch": "Busca de contexto\n(embeddings + grafo)",
            "rank": "Reordenação\n(modelos de linguagem)",
            "write": "Escritor de\nconsultas",
            "valid": "Validadores\n(EXPLAIN, tabelas,\ncolunas, acesso)",
            "research": "Agente\npesquisador",
            "out": "Saída ao\nusuário",
            "p1": "Proposta: validador de\nvalores de filtro",
            "p2": "Proposta: recuperação ciente\nde permissão + auditoria",
            "p3": "Proposta: telemetria de\nerro silencioso",
            "lbl_err": "erros de validação",
            "lbl_ctx": "contexto e recomendação",
            "lbl_hall": "alucinação de esquema",
            "lbl_fixed": "consulta corrigida",
            "fix": "Corretor de\nconsultas",
            "legend_doc": "Documentado pelo caso",
            "legend_prop": "Proposta deste artigo",
        },
        "abl": {
            "ta": "(a) Compilação e nota 4+",
            "tb": "(b) Compila sem nota 4+",
            "x": "% das perguntas",
            "compile": "Compila",
            "q": "Nota 4+ (correta ou quase)",
            "s": "Compila sem nota 4+ (mín.–máx.)",
        },
        "anat": {
            "bar": "Consultas iniciais para um conjunto de perguntas (proporções ilustrativas)",
            "correct": "corretas",
            "visible": "erro visível",
            "silent": "erro silencioso",
            "ceiling": "limite superior do laço: 1 − U",
            "u": "U: erro inicial não sinalizado",
            "fix_c": "corretor conserta (q)",
            "fix_e": "conserto errado silencia (e), além de U",
            "cards": (
                "Três consultas hipotéticas para "
                '"quantos membros ativos do Brasil houve em outubro?"'
            ),
            "ex1": (
                "1. Erro de sintaxe",
                "SELEC COUNT(*)\nFROM membros_ativos",
                "EXPLAIN falha:\nvalidador vê",
            ),
            "ex2": (
                "2. Tabela inexistente",
                "SELECT COUNT(*)\nFROM membros_ativos_v2",
                "índice de tabelas acusa:\nvalidador vê",
            ),
            "ex3": (
                "3. Valor de filtro errado",
                "... WHERE pais =\n'Brasil'",
                "compila, mas o valor\narmazenado é 'BR': conta zero",
            ),
        },
    },
    "en": {
        "right_title": "Model: accuracy by correction rounds (illustrative)",
        "cfg": {
            "A.1": "A.1 schemas only",
            "A.4": "A.4 with examples and attributes",
            "B.1": "B.1 no rankers",
            "B.2": "B.2 no query fixer",
            "B.3": "B.3 with query fixer",
            "Full": "Full",
        },
        "rounds": "Correction rounds (k)",
        "acc": "Probability",
        "sem_acc": "Accuracy, semantic fixer",
        "cmp_acc": "Accuracy, compile-only fixer",
        "cmp_sil": "Silent error, compile-only fixer",
        "ceil": "Ceiling 1 − U",
        "arch": {
            "q": "Question",
            "intent": "Intent\nclassifier",
            "fetch": "Context fetcher\n(embeddings + graph)",
            "rank": "Context\nre-ranker",
            "write": "Query\nwriter",
            "valid": "Validators\n(EXPLAIN, tables,\ncolumns, access)",
            "research": "Researcher\nagent",
            "out": "Output to\nuser",
            "p1": "Proposed: filter-value\nvalidator",
            "p2": "Proposed: permission-aware\nretrieval + audit",
            "p3": "Proposed: silent-error\ntelemetry",
            "lbl_err": "validation errors",
            "lbl_ctx": "context and recommendation",
            "lbl_hall": "schema hallucination",
            "lbl_fixed": "fixed query",
            "fix": "Query\nfixer",
            "legend_doc": "Documented by the case",
            "legend_prop": "Proposed in this article",
        },
        "abl": {
            "ta": "(a) Compilation and rated 4+",
            "tb": "(b) Compiles without a 4+",
            "x": "% of questions",
            "compile": "Compiles",
            "q": "Rated 4+ (correct or almost)",
            "s": "Compiles, not rated 4+ (min–max)",
        },
        "anat": {
            "bar": "Initial queries for a set of questions (illustrative proportions)",
            "correct": "correct",
            "visible": "visible error",
            "silent": "silent error",
            "ceiling": "upper bound of the loop: 1 − U",
            "u": "U: initial error, not flagged",
            "fix_c": "fixer repairs (q)",
            "fix_e": "wrong repair silences (e), on top of U",
            "cards": (
                "Three hypothetical queries for "
                '"how many active members in Brazil were there in October?"'
            ),
            "ex1": (
                "1. Syntax error",
                "SELEC COUNT(*)\nFROM active_members",
                "EXPLAIN fails:\nvalidator sees it",
            ),
            "ex2": (
                "2. Missing table",
                "SELECT COUNT(*)\nFROM active_members_v2",
                "table index flags it:\nvalidator sees it",
            ),
            "ex3": (
                "3. Wrong filter value",
                "... WHERE country =\n'Brazil'",
                "compiles, but the stored\nvalue is 'BR': counts zero",
            ),
        },
    },
}

ORDER = ["A.1", "A.4", "B.1", "B.2", "B.3", "Full"]


def _style() -> None:
    """Apply the shared figure style (serif text to match the article, recessive axes)."""
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
            "font.size": 9,
            "axes.edgecolor": MUTED,
            "axes.labelcolor": INK,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "svg.hashsalt": "self-correction-ceiling",
            "svg.fonttype": "none",
        }
    )


def fig_ceiling(res: dict, lang: str, out: Path) -> list[Path]:
    """Draw the model figure (accuracy by correction rounds, illustrative); return the paths.

    The published ablation is drawn by :func:`fig_ablation`, with the identified range of the
    silent error; this figure no longer stacks it as an exact partition.
    """
    t = TXT[lang]
    fig, ax2 = plt.subplots(figsize=(6.5, 4.8))
    ax2.tick_params(labelsize=10.5)
    ax2.xaxis.label.set_size(11)
    ax2.yaxis.label.set_size(11)

    m = res["model"]
    base = Params(**m["base"])
    ks = list(range(0, 11))
    for name, col, ls, key in (
        ("semantic_fixer", CORRECT, "-", "sem_acc"),
        ("compile_only_fixer", CORRECT, "--", "cmp_acc"),
    ):
        p = base.with_(**m["fixers"][name]["params"])
        ax2.plot(
            ks,
            [accuracy(p.with_(k=k)) for k in ks],
            color=col,
            linestyle=ls,
            linewidth=2,
            marker="o",
            markersize=4,
            label=t[key],
        )
    pc = base.with_(**m["fixers"]["compile_only_fixer"]["params"])
    sil = m["fixers"]["compile_only_fixer"]["silent_error_by_rounds"]
    ks_s = sorted(int(k) for k in sil if int(k) <= 10)
    ax2.plot(
        ks_s,
        [sil[str(k)] for k in ks_s],
        color=SILENT,
        linestyle="--",
        linewidth=2,
        marker="s",
        markersize=4,
        label=t["cmp_sil"],
    )
    ax2.axhline(ceiling(pc), color=INK, linewidth=1, linestyle=":")
    ax2.text(
        10,
        ceiling(pc) + 0.012,
        f"{t['ceil']} = {ceiling(pc):.2f}".replace(".", "," if lang == "pt" else "."),
        ha="right",
        va="bottom",
        fontsize=10.5,
        color=INK,
    )
    ax2.set_ylim(0.2, 0.8)
    ax2.set_xlabel(t["rounds"])
    ax2.set_ylabel(t["acc"])
    ax2.set_title(t["right_title"], fontsize=12, loc="left", color=INK)
    ax2.grid(color=GRID, linewidth=0.6)
    ax2.set_axisbelow(True)
    ax2.legend(
        loc="upper center", bbox_to_anchor=(0.45, -0.16), ncol=1, frameon=False, fontsize=10.5
    )
    if lang == "pt":
        for ax in (ax2,):
            ax.xaxis.set_major_formatter(
                matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:g}".replace(".", ","))
            )
        ax2.yaxis.set_major_formatter(
            matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:.1f}".replace(".", ","))
        )
    fig.tight_layout()
    return _save(fig, out / f"fig_ceiling_{lang}")


def fig_architecture(lang: str, out: Path) -> list[Path]:
    """Draw the write-query flow (documented, solid) and the proposed controls (dashed)."""
    a = TXT[lang]["arch"]
    fig, ax = plt.subplots(figsize=(6.5, 7.4))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 120)
    ax.axis("off")
    # main write-query flow as a vertical column (x, y, w, h in data units)
    boxes = {
        "q": (8, 108, 36, 8),
        "intent": (8, 93, 36, 9),
        "fetch": (8, 78, 36, 9),
        "rank": (8, 63, 36, 9),
        "write": (8, 48, 36, 9),
        "valid": (8, 30, 36, 11),
        "out": (8, 12, 36, 9),
        "fix": (60, 31, 30, 9),
        "research": (60, 52, 30, 9),
    }
    props = {"p2": (60, 78, 36, 9), "p1": (60, 16, 36, 8), "p3": (60, 3, 36, 8)}

    def box(xywh: tuple, label: str, dashed: bool) -> None:
        """Draw one labelled box of the flow diagram."""
        x, y, w, h = xywh
        ax.add_patch(
            FancyBboxPatch(
                (x, y),
                w,
                h,
                boxstyle="round,pad=0.3,rounding_size=0.8",
                facecolor="white",
                edgecolor=CORRECT if not dashed else SILENT,
                linewidth=1.4,
                linestyle="--" if dashed else "-",
            )
        )
        ax.text(x + w / 2, y + h / 2, label, ha="center", va="center", fontsize=8.6, color=INK)

    def arrow(p0: tuple, p1: tuple, dashed: bool = False, rad: float = 0.0) -> None:
        """Draw an arrow between two points of the flow diagram."""
        ax.add_patch(
            FancyArrowPatch(
                p0,
                p1,
                arrowstyle="-|>",
                mutation_scale=9,
                linewidth=1.1,
                color=MUTED,
                linestyle="--" if dashed else "-",
                connectionstyle=f"arc3,rad={rad}",
            )
        )

    for k, v in boxes.items():
        box(v, a[k], False)
    for k, v in props.items():
        box(v, a[k], True)
    for top, bot in (
        ("q", "intent"),
        ("intent", "fetch"),
        ("fetch", "rank"),
        ("rank", "write"),
        ("write", "valid"),
        ("valid", "out"),
    ):
        x, y, w, _ = boxes[top]
        y2 = boxes[bot][1] + boxes[bot][3]
        arrow((x + w / 2, y - 0.6), (x + w / 2, y2 + 0.8))
    arrow((44.6, 37.0), (59.4, 37.0))
    ax.text(52, 38.2, a["lbl_err"], fontsize=7.2, color=MUTED, ha="center", va="bottom")
    arrow((59.4, 32.5), (44.6, 32.5))
    ax.text(52, 31.3, a["lbl_fixed"], fontsize=7.2, color=MUTED, ha="center", va="top")
    arrow((70, 40.6), (70, 51.4))
    ax.text(68.8, 46, a["lbl_hall"], fontsize=7.2, color=MUTED, ha="right", va="center")
    arrow((80, 51.4), (80, 40.6))
    ax.text(81.2, 46, a["lbl_ctx"], fontsize=7.2, color=MUTED, ha="left", va="center")
    arrow((59.6, 82.5), (44.6, 82.5), dashed=True)
    arrow((59.6, 20.0), (44.6, 30.8), dashed=True)
    arrow((59.6, 7.0), (44.6, 15.5), dashed=True)
    handles = [
        plt.Line2D([0], [0], color=CORRECT, linewidth=1.4),
        plt.Line2D([0], [0], color=SILENT, linewidth=1.4, linestyle="--"),
    ]
    ax.legend(
        handles,
        [a["legend_doc"], a["legend_prop"]],
        loc="upper right",
        frameon=False,
        fontsize=8.5,
        bbox_to_anchor=(1.0, 1.0),
    )
    fig.tight_layout()
    return _save(fig, out / f"fig_architecture_{lang}")


def fig_ablation(res: dict, lang: str, out: Path) -> list[Path]:
    """Draw the published ablation without assuming that every query rated 4+ compiles.

    Panel (a): compile and rated-4+ shares per configuration (two markers on one axis). Panel (b):
    the identified range of the silent error S, ``[max(0, C - Q), min(C, 100 - Q)]``.
    """
    t = TXT[lang]["abl"]
    rows = res["linkedin"]["rows"]
    keys = ORDER[::-1]
    fig, (a1, a2) = plt.subplots(
        1, 2, figsize=(6.5, 3.5), sharey=True, gridspec_kw={"width_ratios": [1.25, 1]}
    )
    ys = range(len(keys))
    for y, k in zip(ys, keys, strict=True):
        r = rows[k]
        hl = k in ("B.2", "B.3")
        a1.plot([r["score_4plus"], r["compile"]], [y, y], color=GRID, linewidth=2.2, zorder=1)
        a1.scatter(r["compile"], y, marker="D", s=34, color=VISIBLE, zorder=3)
        a1.scatter(r["score_4plus"], y, marker="o", s=40, color=CORRECT, zorder=3)
        lo, hi = r["silent_error_lower_bound"], r["silent_error_upper_bound"]
        a2.plot(
            [lo, hi],
            [y, y],
            color=SILENT,
            linewidth=6 if hl else 4,
            solid_capstyle="butt",
            alpha=1.0 if hl else 0.55,
        )
        a2.text(hi + 1.5, y, f"{lo}–{hi}", va="center", fontsize=8, color=INK)
    a1.set_yticks(list(ys))
    a1.set_yticklabels([TXT[lang]["cfg"][k] for k in keys], fontsize=8.6)
    for ax, title, xl in ((a1, t["ta"], (0, 100)), (a2, t["tb"], (0, 100))):
        ax.set_xlim(*xl)
        ax.set_title(title, fontsize=9, loc="left")
        ax.set_xlabel(t["x"], fontsize=8.6)
        ax.grid(axis="x", color=GRID, linewidth=0.6)
        ax.set_axisbelow(True)
    handles = [
        plt.Line2D([0], [0], marker="D", color="none", markerfacecolor=VISIBLE, markersize=6),
        plt.Line2D([0], [0], marker="o", color="none", markerfacecolor=CORRECT, markersize=6.5),
        plt.Line2D([0], [0], color=SILENT, linewidth=4),
    ]
    fig.legend(
        handles,
        [t["compile"], t["q"], t["s"]],
        loc="lower center",
        ncol=3,
        frameon=False,
        fontsize=8.4,
        bbox_to_anchor=(0.5, -0.01),
    )
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    return _save(fig, out / f"fig_ablation_{lang}")


def fig_anatomy(lang: str, out: Path) -> list[Path]:
    """Draw the intuition of the ceiling: what the validator sees, what the fixer can move.

    Conceptual, no data: the bar splits the generated queries into correct, visible error and
    silent error; the fixer acts only on the visible part (fixing it or silencing it), so the
    silent part bounds the reachable accuracy. Three illustrative queries show one error of each
    kind (hypothetical schema, not taken from the case).
    """
    t = TXT[lang]["anat"]
    fig, ax = plt.subplots(figsize=(6.5, 3.9))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 60)
    ax.axis("off")
    # (1) the bar of all generated queries
    segs = [
        (0, 44, CORRECT, t["correct"]),
        (44.6, 22, VISIBLE, t["visible"]),
        (67.2, 32.8, SILENT, t["silent"]),
    ]
    for x, w, col, lab in segs:
        ax.add_patch(plt.Rectangle((x, 38), w, 8, facecolor=col, edgecolor="none"))
        ax.text(
            x + w / 2,
            42,
            lab,
            ha="center",
            va="center",
            color="white",
            fontsize=9.4,
            fontweight="bold",
        )
    ax.text(50, 59.5, t["bar"], fontsize=9.4, color=INK, ha="center", va="top")

    def brace(x0: float, x1: float, y: float, label: str, col: str) -> None:
        """Draw a bracket under the bar with a centered label."""
        ax.plot([x0, x0, x1, x1], [y + 1.2, y, y, y + 1.2], color=col, linewidth=1.1)
        ax.text((x0 + x1) / 2, y - 0.8, label, ha="center", va="top", fontsize=9.2, color=col)

    brace(0, 66.6, 35.6, t["ceiling"], CORRECT)
    brace(67.2, 100, 35.6, t["u"], SILENT)
    # (2) the fixer acts on the visible segment only
    ax.add_patch(
        FancyArrowPatch(
            (58, 46.4),
            (22, 46.4),
            arrowstyle="-|>",
            mutation_scale=9,
            linewidth=1.1,
            color=CORRECT,
            connectionstyle="arc3,rad=0.3",
        )
    )
    ax.add_patch(
        FancyArrowPatch(
            (60, 46.4),
            (82, 46.4),
            arrowstyle="-|>",
            mutation_scale=9,
            linewidth=1.1,
            color=SILENT,
            linestyle="--",
            connectionstyle="arc3,rad=-0.3",
        )
    )
    ax.text(40, 54.6, t["fix_c"], fontsize=8.8, color=CORRECT, ha="center", va="center")
    ax.text(71, 52.0, t["fix_e"], fontsize=8.8, color=SILENT, ha="center", va="center")
    # (3) three illustrative queries, one per kind of outcome
    cards = [(1, VISIBLE, t["ex1"]), (34.5, VISIBLE, t["ex2"]), (68, SILENT, t["ex3"])]
    for x, col, (head, sql, verdict) in cards:
        ax.add_patch(
            FancyBboxPatch(
                (x, 1),
                31,
                21,
                boxstyle="round,pad=0.3,rounding_size=0.8",
                facecolor="white",
                edgecolor=col,
                linewidth=1.3,
            )
        )
        ax.text(
            x + 1.4, 20.6, head, fontsize=9.0, color=INK, ha="left", va="top", fontweight="bold"
        )
        ax.text(
            x + 1.4, 15.6, sql, fontsize=9.4, color=INK, ha="left", va="top", family="monospace"
        )
        ax.text(x + 1.4, 7.4, verdict, fontsize=8.8, color=col, ha="left", va="top")
    ax.text(
        50, 25.6, t["cards"], fontsize=8.8, color=MUTED, ha="center", va="center", style="italic"
    )
    fig.tight_layout()
    return _save(fig, out / f"fig_anatomy_{lang}")


def _save(fig: plt.Figure, stem: Path) -> list[Path]:
    """Save PNG (300 dpi, no metadata timestamp) and SVG; return the paths."""
    stem.parent.mkdir(parents=True, exist_ok=True)
    png, svg = stem.with_suffix(".png"), stem.with_suffix(".svg")
    fig.savefig(png, dpi=300, metadata={"Software": None})
    fig.savefig(svg, metadata={"Date": None})
    plt.close(fig)
    return [png, svg]


def main(argv: list[str] | None = None) -> int:
    """Draw both figures for the requested language; return 0."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--results", default=str(ROOT / "output" / "results.json"))
    ap.add_argument("--out", default=str(ROOT / "output" / "figures"))
    ap.add_argument("--lang", choices=sorted(TXT), default="en")
    args = ap.parse_args(argv)
    _style()
    res = json.loads(Path(args.results).read_text(encoding="utf-8"))
    out = Path(args.out)
    figs = fig_anatomy(args.lang, out) + fig_ablation(res, args.lang, out)
    figs += fig_ceiling(res, args.lang, out)
    for p in figs + fig_architecture(args.lang, out):
        print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
