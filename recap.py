#!/usr/bin/env python3
"""
Récapitulatif de tous les runs de bench.py : un document Typst, compilé en PDF
si `typst` est installé.

    python3 recap.py                      # tous les runs de runs/
    python3 recap.py runs/2026* -o recap.typ
    python3 recap.py --backend ollama --mode direct

Chaque run est un dossier `runs/<horodatage>/` contenant `results.json`. Un même
couple (modèle, tâche, mode) peut avoir été mesuré plusieurs fois : on ne garde
que le résultat **le plus récent**, et seulement à machine, hôte et backend
identiques — deux mesures faites sur des machines ou des backends différents ne
s'écrasent pas, elles sont rapportées côte à côte.

Le tableau met un modèle par colonne et un test (tâche × mode) par ligne.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUNS = ROOT / "runs"
MODES = ("direct", "agentic")

# libellé et couleur par statut : en PDF, un mot coloré se lit mieux qu'un
# émoji, qui manquerait de toute façon dans les polices par défaut de Typst
STATUT = {
    "pass": ("OK", '#1a7f37'),
    "fail": ("KO tests", '#c0392b'),
    "compile_error": ("KO compil", '#b35309'),
    "no_code": ("KO vide", '#6b6b6b'),
    "timeout": ("KO délai", '#8a6d1f'),
    "error": ("KO backend", '#7d3c98'),
}
INCONNU = ("KO ?", '#6b6b6b')
# statuts qui ne valent pas la peine d'afficher un score de tests
SANS_SCORE = {"no_code", "error"}

# séquences d'échappement reconnues par Typst ; les noms de tâches contiennent
# des « _ », qui sinon passeraient pour de l'italique
ECHAPPES = {c: "\\" + c for c in "\\#$*_`<>@~[]"}


# --------------------------------------------------------------------------- #
# Lecture des runs
# --------------------------------------------------------------------------- #

def datation(run: Path) -> tuple:
    """Clé de récence d'un run : son horodatage de nom, sinon la date du fichier."""
    try:
        return (datetime.strptime(run.name[:15], "%Y%m%d-%H%M%S").timestamp(), run.name)
    except ValueError:
        try:
            return ((run / "results.json").stat().st_mtime, run.name)
        except OSError:
            return (0.0, run.name)


def backend_effectif(model: str, config: dict) -> str:
    """Le backend réellement utilisé pour ce modèle, préfixe compris."""
    if model.startswith("claude:"):
        return "claude-cli"
    if model.startswith("litellm:"):
        return "litellm"
    return config.get("backend") or "ollama"


def lire(run: Path) -> tuple[dict, list] | None:
    """(config, résultats) d'un run, ou None s'il n'est pas exploitable."""
    fichier = run / "results.json"
    if not fichier.is_file():
        return None
    try:
        charge = json.loads(fichier.read_text(encoding="utf-8"))
        return charge.get("config") or {}, list(charge.get("results") or [])
    except Exception as exc:  # run interrompu, JSON tronqué, droits manquants…
        print(f"[recap] {fichier} ignoré : {type(exc).__name__}: {exc}", file=sys.stderr)
        return None


def collecter(runs: list[Path]) -> dict[tuple, dict]:
    """Une ligne par (machine, hôte, backend, modèle, tâche, mode) : la plus récente."""
    retenus: dict[tuple, dict] = {}
    for run in sorted(runs, key=datation):  # du plus ancien au plus récent
        lu = lire(run)
        if lu is None:
            continue
        config, resultats = lu
        machine = config.get("machine") or "?"
        host = config.get("host") or "?"
        for r in resultats:
            modele, tache, mode = r.get("model"), r.get("task"), r.get("mode")
            if not (modele and tache and mode):
                continue
            r = dict(r, _run=run.name, _machine=machine, _host=host,
                     _backend=backend_effectif(modele, config))
            retenus[(machine, host, r["_backend"], modele, tache, mode)] = r
    return retenus


# --------------------------------------------------------------------------- #
# Rendu
# --------------------------------------------------------------------------- #

def duree(secondes: float) -> str:
    # arrondi d'abord, sinon 3599,6 s donnerait « 59m60 »
    minutes, reste = divmod(round(secondes), 60)
    return f"{reste}s" if not minutes else f"{minutes}m{reste:02d}"


def tours(n: int) -> str:
    return f"{n} tour" if n == 1 else f"{n} tours"


def typ(texte) -> str:
    """Texte brut échappé pour du contenu Typst."""
    return "".join(ECHAPPES.get(c, c) for c in str(texte))


def mono(texte) -> str:
    """Nom de modèle ou de tâche, en chasse fixe (chaîne Typst, pas du markup)."""
    litteral = str(texte).replace("\\", "\\\\").replace('"', '\\"')
    return f'#raw("{litteral}")'


def cellule(r: dict | None) -> str:
    """`OK · 12/12 · 45s · 3 tours`, le statut coloré disant *pourquoi* si KO."""
    if r is None:
        return "—"
    libelle, couleur = STATUT.get(r.get("status", ""), INCONNU)
    bouts = [f'#text(fill: rgb("{couleur}"))[{typ(libelle)}]']
    if r.get("status") not in SANS_SCORE and r.get("total"):
        bouts.append(f"{r.get('passed', 0)}/{r['total']}")
    bouts.append(duree(r.get("wall_s", 0.0)))
    if r.get("turns"):
        bouts.append(tours(r["turns"]))
    return " · ".join(bouts)


def tableau(lignes: list[str], entetes: list[str], corps: list[list[str]],
            fixes: int, secable: bool = True) -> None:
    """Un tableau Typst : `fixes` colonnes de gauche au plus juste, le reste réparti."""
    colonnes = ", ".join(["auto"] * fixes + ["1fr"] * (len(entetes) - fixes))
    # le tableau de cumuls tient toujours sur une page : le couper y laisserait une
    # ou deux lignes orphelines. `breakable` est une propriété du bloc, pas du tableau.
    if not secable:
        lignes.append("#block(breakable: false)[")
    lignes.append("#table(")
    lignes.append(f"  columns: ({colonnes}),")
    lignes.append("  table.header(" + ", ".join(f"[{c}]" for c in entetes) + "),")
    for ligne in corps:
        lignes.append("  " + ", ".join(f"[{c}]" for c in ligne) + ",")
    lignes.append(")")
    if not secable:
        lignes.append("]")
    lignes.append("")


PREAMBULE = '''// Document engendré par recap.py — ne pas éditer à la main.
#set document(title: "Récapitulatif des runs", author: "bench.py")
#set page(
  paper: "a4",
  flipped: true,
  margin: 1.2cm,
  footer: context align(center, text(size: 7pt, fill: luma(120))[
    #counter(page).display("1 / 1", both: true)
  ]),
)
#set text(size: 8pt, lang: "fr")
#set table(
  stroke: 0.4pt + luma(200),
  inset: 5pt,
  fill: (_, y) => if y == 0 { luma(238) },
)
#show table.cell.where(y: 0): strong
#show heading.where(level: 1): it => block(below: 0.8em)[#text(size: 15pt)[#it.body]]
#show heading.where(level: 2): it => block(above: 1.6em, below: 0.7em)[
  #text(size: 11pt)[#it.body]
]
'''


def recapitulatif(retenus: dict[tuple, dict], modes: tuple[str, ...]) -> str:
    out = [PREAMBULE, "= Récapitulatif des runs", ""]
    if not retenus:
        out.append("_Aucun résultat._")
        return "\n".join(out) + "\n"

    engendre = datetime.now().strftime("%Y-%m-%d %H:%M")
    out.append(f"#text(fill: luma(100))[Engendré le {engendre} · "
               f"{len(retenus)} mesures retenues]")
    out.append("")

    # une section par contexte de mesure : mélanger les machines ou les backends
    # dans un même tableau ferait comparer ce qui n'est pas comparable
    contextes = sorted({(r["_machine"], r["_host"], r["_backend"]) for r in retenus.values()})
    for machine, host, backend in contextes:
        lot = {k: r for k, r in retenus.items()
               if (r["_machine"], r["_host"], r["_backend"]) == (machine, host, backend)}
        modeles = sorted({r["model"] for r in lot.values()})
        taches = sorted({r["task"] for r in lot.values()})
        # une ligne par test, c'est-à-dire par couple (tâche, mode) mesuré
        essais = [(t, m) for t in taches for m in modes
                  if any(r["task"] == t and r["mode"] == m for r in lot.values())]

        out.append(f"== {typ(backend)} — {typ(machine)}")
        out.append("")
        out.append(f"#text(fill: luma(100))[Hôte : {mono(host)} · {len(modeles)} modèle(s) · "
                   f"{len(taches)} tâche(s) · {len(lot)} mesure(s) retenue(s)]")
        out.append("")

        par_cle = {(r["model"], r["task"], r["mode"]): r for r in lot.values()}
        corps = []
        for tache, mode in essais:
            ligne = [mono(tache), typ(mode)]
            for modele in modeles:
                ligne.append(cellule(par_cle.get((modele, tache, mode))))
            corps.append(ligne)
        tableau(out, ["tâche", "mode"] + [mono(m) for m in modeles], corps, fixes=2)

        # totaux, dans le même sens de lecture : un modèle par colonne
        corps = []
        for mode in modes:
            par_modele = {m: [r for r in lot.values() if r["model"] == m and r["mode"] == mode]
                          for m in modeles}
            if not any(par_modele.values()):
                continue
            for intitule, calcul in (
                ("tâches OK", lambda v: f"{sum(1 for r in v if r.get('status') == 'pass')}/{len(v)}"),
                ("tests passés", lambda v: (f"{sum(r.get('passed', 0) for r in v)}"
                                            f"/{sum(r.get('total', 0) for r in v)}"
                                            if sum(r.get("total", 0) for r in v) else "—")),
                ("temps cumulé", lambda v: duree(sum(r.get("wall_s", 0.0) for r in v))),
                ("tours cumulés", lambda v: str(sum(r.get("turns", 0) or 0 for r in v))),
            ):
                corps.append([typ(mode), typ(intitule)]
                             + [calcul(par_modele[m]) if par_modele[m] else "—" for m in modeles])
        cumuls = {m: [r for r in lot.values() if r["model"] == m] for m in modeles}
        corps.append(["", "tokens générés"]
                     + [str(sum(r.get("gen_tokens", 0) or 0 for r in cumuls[m])) for m in modeles])
        couts = {m: sum(r.get("cost_usd", 0.0) or 0.0 for r in cumuls[m]) for m in modeles}
        corps.append(["", "coût"]
                     + [f"{couts[m]:.2f} \\$" if couts[m] else "—" for m in modeles])
        tableau(out, ["mode", "cumul"] + [mono(m) for m in modeles], corps, fixes=2,
                secable=False)

    legende = " · ".join(f'#text(fill: rgb("{c}"))[{typ(l)}] {mono(statut)}'
                         for statut, (l, c) in STATUT.items())
    out.append(f"#text(size: 7pt)[Légende : {legende}]")
    out.append("")
    out.append("#text(size: 7pt)[Chaque cellule est la mesure #strong[la plus récente] pour ce "
               "couple (modèle, tâche, mode) sur cette machine, cet hôte et ce backend, au "
               "format `statut · tests passés/total · temps mur · tours`.]")
    out.append("")
    return "\n".join(out) + "\n"


def compiler(source: Path) -> Path | None:
    """Compile le .typ en PDF si `typst` est là. Renvoie le PDF, ou None."""
    typst = shutil.which("typst")
    if typst is None:
        print("[recap] typst introuvable : PDF non engendré "
              "(brew install typst, ou https://typst.app)", file=sys.stderr)
        return None
    pdf = source.with_suffix(".pdf")
    try:
        proc = subprocess.run([typst, "compile", str(source), str(pdf)],
                              capture_output=True, text=True, timeout=120)
    except Exception as exc:
        print(f"[recap] typst n'a pas pu être lancé : {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return None
    if proc.returncode != 0:
        print(f"[recap] typst a échoué (code {proc.returncode}) :\n"
              f"{(proc.stderr or proc.stdout).strip()}", file=sys.stderr)
        return None
    return pdf


# --------------------------------------------------------------------------- #

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="*", help="dossiers de run (défaut : tous ceux de runs/)")
    ap.add_argument("-o", "--out", default=str(RUNS / "recapitulatif.typ"),
                    help="fichier Typst à écrire (défaut : runs/recapitulatif.typ) ; "
                         "le PDF prend le même nom en .pdf")
    ap.add_argument("--machine", help="ne garder que cette machine (sous-chaîne)")
    ap.add_argument("--host", help="ne garder que cet hôte (sous-chaîne)")
    ap.add_argument("--backend", help="ne garder que ce backend (ollama, litellm, claude-cli)")
    ap.add_argument("--models", help="modèles à garder, séparés par des virgules")
    ap.add_argument("--tasks", help="tâches à garder, séparées par des virgules")
    ap.add_argument("--mode", choices=MODES, help="ne garder qu'un mode")
    ap.add_argument("--print", dest="afficher", action="store_true",
                    help="afficher la source Typst sur la sortie standard")
    ap.add_argument("--no-pdf", action="store_true", help="écrire le .typ sans compiler")
    args = ap.parse_args()

    if args.runs:
        dossiers = [Path(a) if Path(a).is_dir() else RUNS / a for a in args.runs]
        manquants = [a for a, d in zip(args.runs, dossiers) if not d.is_dir()]
        if manquants:
            sys.exit("dossiers introuvables : " + ", ".join(manquants))
    elif RUNS.is_dir():
        dossiers = [d for d in RUNS.iterdir() if d.is_dir() and not d.name.startswith("_")]
    else:
        sys.exit(f"{RUNS} n'existe pas")

    retenus = collecter(dossiers)

    modeles = set(args.models.split(",")) if args.models else None
    taches = set(args.tasks.split(",")) if args.tasks else None
    filtres = {
        "_machine": lambda v: args.machine is None or args.machine.lower() in v.lower(),
        "_host": lambda v: args.host is None or args.host.lower() in v.lower(),
        "_backend": lambda v: args.backend is None or args.backend.lower() in v.lower(),
        "model": lambda v: modeles is None or v in modeles,
        "task": lambda v: taches is None or v in taches,
        "mode": lambda v: args.mode is None or v == args.mode,
    }
    retenus = {k: r for k, r in retenus.items()
               if all(test(r.get(champ, "")) for champ, test in filtres.items())}

    modes = (args.mode,) if args.mode else MODES
    texte = recapitulatif(retenus, modes)

    source = Path(args.out)
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(texte, encoding="utf-8")
    if args.afficher:
        print(texte)
    print(f"[recap] {len(retenus)} mesure(s) retenue(s) → {source}", file=sys.stderr)

    if args.no_pdf:
        return 0
    pdf = compiler(source)
    if pdf is not None:
        print(f"[recap] PDF → {pdf}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
