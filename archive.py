#!/usr/bin/env python3
"""
Met de côté les mesures d'un modèle, sans les perdre.

    python3 archive.py --models muse-glimmer:latest,qwen3.8:27b
    python3 archive.py --liste
    python3 archive.py --restaurer --models qwen3.8:27b

Les mesures partent dans `runs/_archive/<run>/` : `recap.py` et `bench.py`
ignorent les dossiers commençant par `_`, le récapitulatif s'allège donc sans
que rien ne soit effacé, et `--restaurer` remet tout en place.

Un run dont toutes les mesures sont archivées part en entier, `report.md`
compris. Un run seulement écorné garde son `report.md` d'origine : il décrit
alors des mesures qui ne sont plus dans son `results.json`.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUNS = ROOT / "runs"
ARCHIVE = RUNS / "_archive"
MANIFESTE = "_archive.json"


def slug(modele: str, tache: str, mode: str) -> str:
    """Le nom du dossier de travail, tel que bench.py le fabrique."""
    return f"{modele}__{tache}__{mode}".replace(":", "_").replace("/", "-")


def charger(fichier: Path) -> dict:
    return json.loads(fichier.read_text(encoding="utf-8"))


def ecrire(fichier: Path, charge: dict) -> None:
    fichier.write_text(json.dumps(charge, indent=2, ensure_ascii=False), encoding="utf-8")


def runs_lisibles(racine: Path) -> list[Path]:
    if not racine.is_dir():
        return []
    return sorted(d for d in racine.iterdir()
                  if d.is_dir() and (d / "results.json").is_file())


# --------------------------------------------------------------------------- #

def archiver(modeles: set[str], simuler: bool) -> int:
    deplaces = 0
    for run in runs_lisibles(RUNS):
        if run.name.startswith("_"):
            continue
        charge = charger(run / "results.json")
        resultats = charge.get("results") or []
        partent = [r for r in resultats if r.get("model") in modeles]
        if not partent:
            continue
        restent = [r for r in resultats if r.get("model") not in modeles]
        entier = not restent
        cible = ARCHIVE / run.name
        noms = sorted({r["model"] for r in partent})
        print(f"{run.name} : {len(partent)} mesure(s), {', '.join(noms)}"
              f"{' — run entier' if entier else ''}")
        deplaces += len(partent)
        if simuler:
            continue

        ARCHIVE.mkdir(parents=True, exist_ok=True)
        if entier:
            # rien ne reste : le run part tel quel, report.md et tout le reste
            if cible.exists():
                shutil.rmtree(cible)
            shutil.move(str(run), str(cible))
            manifeste = {"entier": True, "modeles": noms}
        else:
            cible.mkdir(parents=True, exist_ok=True)
            ancien = charger(cible / "results.json") if (cible / "results.json").is_file() else {}
            ecrire(cible / "results.json",
                   {"config": charge.get("config") or {},
                    "results": (ancien.get("results") or []) + partent})
            for r in partent:
                dossier = run / slug(r["model"], r["task"], r["mode"])
                if dossier.is_dir():
                    destination = cible / dossier.name
                    if destination.exists():
                        shutil.rmtree(destination)
                    shutil.move(str(dossier), str(destination))
            ecrire(run / "results.json", {"config": charge.get("config") or {},
                                          "results": restent})
            precedent = charger(cible / MANIFESTE) if (cible / MANIFESTE).is_file() else {}
            manifeste = {"entier": False,
                         "modeles": sorted(set(precedent.get("modeles") or []) | set(noms))}
        manifeste["archive_le"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        ecrire(cible / MANIFESTE, manifeste)
    return deplaces


def restaurer(modeles: set[str] | None, simuler: bool) -> int:
    rendus = 0
    for cible in runs_lisibles(ARCHIVE):
        manifeste = charger(cible / MANIFESTE) if (cible / MANIFESTE).is_file() else {}
        charge = charger(cible / "results.json")
        resultats = charge.get("results") or []
        reviennent = [r for r in resultats
                      if modeles is None or r.get("model") in modeles]
        if not reviennent:
            continue
        run = RUNS / cible.name
        print(f"{cible.name} : {len(reviennent)} mesure(s) rendue(s)")
        rendus += len(reviennent)
        if simuler:
            continue

        if manifeste.get("entier") and len(reviennent) == len(resultats):
            (cible / MANIFESTE).unlink(missing_ok=True)
            shutil.move(str(cible), str(run))
            continue

        run.mkdir(parents=True, exist_ok=True)
        if (run / "results.json").is_file():
            avant = charger(run / "results.json")
            config = avant.get("config") or charge.get("config") or {}
            garde = avant.get("results") or []
        else:
            config, garde = charge.get("config") or {}, []
        ecrire(run / "results.json", {"config": config, "results": garde + reviennent})
        for r in reviennent:
            dossier = cible / slug(r["model"], r["task"], r["mode"])
            if dossier.is_dir():
                destination = run / dossier.name
                if destination.exists():
                    shutil.rmtree(destination)
                shutil.move(str(dossier), str(destination))
        restent = [r for r in resultats if r not in reviennent]
        if restent:
            ecrire(cible / "results.json", {"config": charge.get("config") or {},
                                            "results": restent})
        else:
            shutil.rmtree(cible)
    if ARCHIVE.is_dir() and not any(ARCHIVE.iterdir()):
        ARCHIVE.rmdir()  # plus rien de côté : pas de dossier vide qui traîne
    return rendus


def lister() -> int:
    runs = runs_lisibles(ARCHIVE)
    if not runs:
        print(f"{ARCHIVE} : rien d'archivé")
        return 0
    total = 0
    for cible in runs:
        manifeste = charger(cible / MANIFESTE) if (cible / MANIFESTE).is_file() else {}
        resultats = charger(cible / "results.json").get("results") or []
        total += len(resultats)
        entier = " (run entier)" if manifeste.get("entier") else ""
        print(f"{cible.name}{entier} · {len(resultats)} mesure(s) · "
              f"archivé le {manifeste.get('archive_le', '?')}")
        for modele in sorted({r.get('model') for r in resultats}):
            n = sum(1 for r in resultats if r.get("model") == modele)
            print(f"    {modele} ({n})")
    print(f"\n{total} mesure(s) archivée(s) dans {ARCHIVE}")
    return total


# --------------------------------------------------------------------------- #

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", help="modèles à archiver (ou à restaurer), "
                                     "séparés par des virgules")
    ap.add_argument("--restaurer", action="store_true",
                    help="remettre en place au lieu d'archiver (tout, sans --models)")
    ap.add_argument("--liste", action="store_true", help="ce qui est archivé")
    ap.add_argument("-n", "--simuler", action="store_true",
                    help="dire ce qui bougerait, sans rien déplacer")
    args = ap.parse_args()

    if args.liste:
        lister()
        return 0
    modeles = {m.strip() for m in (args.models or "").split(",") if m.strip()}
    if args.restaurer:
        rendus = restaurer(modeles or None, args.simuler)
        print(f"{rendus} mesure(s) {'à rendre' if args.simuler else 'rendue(s)'}")
        return 0
    if not modeles:
        sys.exit("indique les modèles : --models muse-glimmer:latest,qwen3.8:27b")
    deplaces = archiver(modeles, args.simuler)
    print(f"{deplaces} mesure(s) {'à archiver' if args.simuler else 'archivée(s)'} "
          f"dans {ARCHIVE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
