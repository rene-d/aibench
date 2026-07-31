#!/usr/bin/env python3
"""
Fusionne plusieurs runs de bench.py en un seul tableau comparatif.

    python3 compare.py runs/20260731-023543 runs/20260731-025809
    python3 compare.py            # les 2 runs les plus récents

Rappel de lecture : le mode `direct` est comparable entre tous les backends
(mêmes prompts, aucun outil). Le mode `agentic` l'est entre `ollama` et
`litellm:` (même boucle, mêmes outils) mais pas avec `claude:`, qui apporte les
siens. Et `tok/s` n'a pas la même définition partout : décodage pur côté Ollama,
temps bout en bout réseau compris côté `litellm:` et CLI Claude Code.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUNS = ROOT / "runs"

ICON = {"pass": "✅", "fail": "❌", "compile_error": "🧱", "no_code": "∅",
        "timeout": "⏱", "error": "💥"}


def load(dirs: list[Path]) -> list[dict]:
    rows = []
    for d in dirs:
        f = d / "results.json"
        if not f.exists():
            sys.exit(f"pas de results.json dans {d}")
        payload = json.loads(f.read_text())
        for r in payload["results"]:
            r["_run"] = d.name
            rows.append(r)
    return rows


def dedup(rows: list[dict]) -> list[dict]:
    """Une seule ligne par (modèle, tâche, mode) : la plus récente."""
    keep: dict[tuple, dict] = {}
    for r in rows:
        keep[(r["model"], r["task"], r["mode"])] = r
    return list(keep.values())


def main() -> int:
    if len(sys.argv) > 1:
        dirs = [Path(a) if Path(a).exists() else RUNS / a for a in sys.argv[1:]]
    else:
        dirs = sorted([d for d in RUNS.iterdir() if d.is_dir() and not d.name.startswith("_")])[-2:]
    if len(dirs) < 1:
        sys.exit("aucun run à comparer")

    rows = load(dirs)
    models = sorted({r["model"] for r in rows})
    tasks = sorted({r["task"] for r in rows})

    out = ["# Comparatif\n", f"Runs : {', '.join(d.name for d in dirs)}\n"]

    for mode in ("direct", "agentic"):
        sub = [r for r in rows if r["mode"] == mode]
        if not sub:
            continue
        out.append(f"## Mode {mode}\n")
        out.append("| tâche | " + " | ".join(f"`{m}`" for m in models) + " |")
        out.append("|---" * (len(models) + 1) + "|")
        for task in tasks:
            cells = []
            for m in models:
                # en cas de doublon (même modèle/tâche dans deux runs), le plus récent gagne
                hits = [r for r in sub if r["model"] == m and r["task"] == task]
                hit = hits[-1] if hits else None
                if hit is None:
                    cells.append("—")
                else:
                    cells.append(f"{ICON.get(hit['status'], '?')} {hit['passed']}/{hit['total']} · "
                                 f"{hit['wall_s']:.0f}s · {hit['gen_tokens']} tok")
            out.append(f"| {task} | " + " | ".join(cells) + " |")
        out.append("")

        out.append("| modèle | réussite | tests passés | temps total | tokens générés | coût notionnel |")
        out.append("|---|---|---|---|---|---|")
        for m in models:
            mine = dedup([r for r in sub if r["model"] == m])
            if not mine:
                continue
            npass = sum(1 for r in mine if r["status"] == "pass")
            cost = sum(r.get("cost_usd", 0.0) for r in mine)
            tp = sum(r["passed"] for r in mine)
            tt = sum(r["total"] for r in mine)
            out.append(f"| `{m}` | {npass}/{len(mine)} | {tp}/{tt} "
                       f"| {sum(r['wall_s'] for r in mine):.0f}s "
                       f"| {sum(r['gen_tokens'] for r in mine)} "
                       f"| {('%.2f $' % cost) if cost else '— (local)'} |")
        out.append("")

    out.append("> `direct` est comparable entre tous les backends (mêmes prompts, aucun "
               "outil). `agentic` l'est entre Ollama et `litellm:` (même boucle, mêmes "
               "outils), pas avec `claude:` qui apporte les siens. `tok/s` : décodage pur "
               "côté Ollama, temps bout en bout réseau compris côté `litellm:` et CLI "
               "Claude Code.\n")

    text = "\n".join(out)
    (RUNS / "comparatif.md").write_text(text)
    print(text)
    print(f"Écrit dans {RUNS / 'comparatif.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
