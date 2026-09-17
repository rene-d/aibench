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

Un seul mode est rapporté, `agentic` par défaut : c'est le seul qui exerce la
boucle d'outils, et mêler les deux doublait la hauteur du tableau pour des
mesures qui ne se comparent pas. `--mode direct` rapporte l'autre.

Chaque contexte de mesure donne deux vues : un **classement**, un modèle par
ligne, et le **détail** tâche par tâche, un modèle par colonne — par paquets de
quelques modèles, quitte à tenir sur plusieurs pages, plutôt qu'un seul tableau
illisible quand les modèles se comptent par dizaines.
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
# fiches relevées après coup, quand les runs n'en portent pas : {hôte: {modèle: fiche}}
CACHE = RUNS / "_modeles.json"
MODES = ("agentic", "direct")
MODE_DEFAUT = "agentic"

# au-delà, les colonnes deviennent trop étroites pour une cellule d'une ligne :
# on repart sur un nouveau tableau, page suivante s'il le faut
MODELES_PAR_TABLEAU = 6

# libellé, couleur du texte, teinte de fond et explication par statut : en PDF,
# un mot coloré se lit mieux qu'un émoji, qui manquerait de toute façon dans les
# polices par défaut de Typst ; la teinte donne la carte de chaleur qui permet
# de repérer un modèle ou une tâche d'un coup d'œil, sans lire les cellules
STATUT = {
    "pass":          ("OK",         "#1a7f37", "#e8f4ea", "tous les tests passent"),
    "fail":          ("KO tests",   "#c0392b", "#fdeceb", "des tests échouent"),
    "turns":         ("KO tours",   "#2c5aa0", "#eaf0f8", "à court de tours"),
    "compile_error": ("KO compil",  "#b35309", "#fdf1e4", "ne compile pas"),
    "no_code":       ("KO vide",    "#6b6b6b", "#f2f2f2", "aucun code produit"),
    "timeout":       ("KO délai",   "#8a6d1f", "#faf4de", "délai dépassé"),
    "error":         ("KO backend", "#7d3c98", "#f6eefa", "erreur du backend"),
}
INCONNU = ("KO ?", "#6b6b6b", "#f2f2f2", "statut inconnu")
# statuts qui ne valent pas la peine d'afficher un score de tests
SANS_SCORE = {"no_code", "error"}

# séquences d'échappement reconnues par Typst ; les noms de tâches contiennent
# des « _ », qui sinon passeraient pour de l'italique
ECHAPPES = {c: "\\" + c for c in "\\#$*_`<>@~[]"}
# espace fine insécable, pour les milliers et devant « % »
FINE = " "
# césure possible mais invisible : un nom de modèle sans tiret déborderait sinon
# de sa colonne au lieu de passer à la ligne
COUPURE = "\\u{200b}"


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


def collecter(runs: list[Path]) -> tuple[dict[tuple, dict], dict[tuple, dict]]:
    """Les mesures les plus récentes, et la fiche des modèles qui les ont produites.

    Une mesure par (machine, hôte, backend, profil, modèle, tâche, mode, graine) ;
    une fiche par (machine, hôte, backend, modèle), relevée par `ollama show`.

    La graine fait partie de la clé : deux tirages du même couple sont deux
    mesures, pas une qui écrase l'autre — c'est ce qui permet de donner un écart
    plutôt qu'un chiffre isolé. Le profil agentique aussi : `cc` et `kilo` ne se
    comparent pas ligne à ligne, ils se comparent tableau à tableau.
    """
    retenus: dict[tuple, dict] = {}
    fiches: dict[tuple, dict] = {}
    for run in sorted(runs, key=datation):  # du plus ancien au plus récent
        lu = lire(run)
        if lu is None:
            continue
        config, resultats = lu
        machine = config.get("machine") or "?"
        host = config.get("host") or "?"
        details = config.get("model_details") or {}
        for r in resultats:
            modele, tache, mode = r.get("model"), r.get("task"), r.get("mode")
            if not (modele and tache and mode):
                continue
            profil = r.get("profile") or config.get("agent_profile") or ""
            r = dict(r, _run=run.name, _machine=machine, _host=host, _profil=profil,
                     _backend=backend_effectif(modele, config))
            graine = r.get("seed", 0)
            retenus[(machine, host, r["_backend"], profil, modele, tache, mode, graine)] = r
            if details.get(modele):
                fiches[(machine, host, r["_backend"], modele)] = details[modele]
    return retenus, fiches


# --------------------------------------------------------------------------- #
# Fiches de modèles : celles des runs, complétées à la demande par le serveur
# --------------------------------------------------------------------------- #

def lire_cache() -> dict:
    """Le cache des fiches sondées après coup : {hôte: {modèle: fiche}}."""
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception as exc:
        print(f"[recap] {CACHE} illisible : {type(exc).__name__}: {exc}", file=sys.stderr)
        return {}


def sonder(retenus: dict[tuple, dict], fiches: dict[tuple, dict]) -> dict:
    """Demande au serveur Ollama la fiche des modèles qu'aucun run n'a consignée.

    Les runs d'avant `--no-show` n'ont rien gardé des poids mesurés ; plutôt que
    de tout refaire tourner, on interroge le serveur maintenant et on garde la
    réponse dans `runs/_modeles.json`, réutilisable quand il sera éteint.
    """
    try:
        from bench import sonder_modeles  # même sonde qu'à l'exécution du bench
    except Exception as exc:
        print(f"[recap] sonde indisponible ({type(exc).__name__}: {exc})", file=sys.stderr)
        return lire_cache()

    manquants: dict[str, set] = {}
    for r in retenus.values():
        if r["_backend"] != "ollama":
            continue  # litellm et le CLI Claude ne servent pas de fiche
        if (r["_machine"], r["_host"], r["_backend"], r["model"]) not in fiches:
            manquants.setdefault(r["_host"], set()).add(r["model"])

    cache = lire_cache()
    trouves = 0
    for host, modeles in sorted(manquants.items()):
        print(f"[recap] sonde {host} : {len(modeles)} modèle(s) sans fiche…", file=sys.stderr)
        releve = sonder_modeles(host, sorted(modeles))
        trouves += len(releve)
        if releve:
            cache.setdefault(host, {}).update(releve)
    if trouves:
        CACHE.write_text(json.dumps(cache, indent=1, ensure_ascii=False, sort_keys=True) + "\n",
                         encoding="utf-8")
        print(f"[recap] {trouves} fiche(s) → {CACHE}", file=sys.stderr)
    elif manquants:
        print("[recap] aucune fiche relevée (serveur injoignable ?)", file=sys.stderr)
    return cache


# --------------------------------------------------------------------------- #
# Mise en forme des valeurs
# --------------------------------------------------------------------------- #

def duree(secondes: float) -> str:
    # arrondi d'abord, sinon 3599,6 s donnerait « 59m60 »
    minutes, reste = divmod(round(secondes), 60)
    if minutes < 60:
        return f"{reste}s" if not minutes else f"{minutes}m{reste:02d}"
    heures, minutes = divmod(minutes, 60)
    return f"{heures}h{minutes:02d}"


def tours(n: int) -> str:
    return f"{n} tour" if n == 1 else f"{n} tours"


def entier(n: int) -> str:
    """12345 → « 12 345 », l'espace étant fine et insécable."""
    return f"{n:,}".replace(",", FINE)


def part(numerateur: float, denominateur: float) -> str:
    return f"{100 * numerateur / denominateur:.0f}{FINE}%" if denominateur else "—"


def octets(n: int) -> str:
    return f"{n / 1e9:.1f} Go" if n else "—"


def contexte(n: int) -> str:
    if not n:
        return "—"
    return f"{n // 1024} k" if n % 1024 == 0 else entier(n)


def typ(texte) -> str:
    """Texte brut échappé pour du contenu Typst."""
    return "".join(ECHAPPES.get(c, c) for c in str(texte))


def mono(texte, coupable: bool = False) -> str:
    """Nom de modèle ou de tâche, en chasse fixe (chaîne Typst, pas du markup)."""
    litteral = str(texte).replace("\\", "\\\\").replace('"', '\\"')
    if coupable:  # Typst ne coupe que sur les tirets : offrons-lui les autres
        for c in ":/._":
            litteral = litteral.replace(c, c + COUPURE)
    return f'#raw("{litteral}")'


def gris(texte: str, taille: float = 7.0) -> str:
    return f'#text(size: {taille}pt, fill: luma(110))[{texte}]'


def barre_empilee(mesures: list[dict], largeur: float = 5.4) -> str:
    """Le profil d'un modèle : la part de chaque statut, dans l'ordre de la légende."""
    total = len(mesures) or 1
    comptes = {statut: sum(1 for r in mesures if r.get("status") == statut)
               for statut in STATUT}
    segments = [(comptes[s], STATUT[s][1]) for s in STATUT if comptes[s]]
    reste = total - sum(comptes.values())  # statuts sortis depuis cette version
    if reste > 0:
        segments.append((reste, INCONNU[1]))
    boites = ", ".join(f'box(width: {n / total * largeur:.3f}cm, height: 6pt, '
                       f'fill: rgb("{couleur}"))' for n, couleur in segments)
    return f"#stack(dir: ltr, {boites})"


def cel(contenu: str, fond: str | None = None, portee: int = 1) -> str:
    """Une cellule Typst, éventuellement teintée ou étendue sur plusieurs colonnes."""
    options = []
    if portee > 1:
        options.append(f"colspan: {portee}")
    if fond:
        options.append(f'fill: rgb("{fond}")')
    if options:
        return f'table.cell({", ".join(options)})[{contenu}]'
    return f"[{contenu}]"


def cellule_groupe(tirages: list[dict]) -> str:
    """Plusieurs tirages du même couple : la part de réussite, pas un verdict."""
    if len(tirages) == 1:
        return cellule(tirages[0])
    ok = sum(1 for r in tirages if r.get("status") == "pass")
    # le statut montré est le plus fréquent parmi les échecs : c'est lui qui
    # dit quoi corriger, alors que « 2/3 » ne dit que l'instabilité
    echecs = [r.get("status", "") for r in tirages if r.get("status") != "pass"]
    dominant = max(set(echecs), key=echecs.count) if echecs else "pass"
    libelle, couleur, teinte, _ = STATUT.get(dominant, INCONNU)
    if ok == len(tirages):
        tete = f'#text(fill: rgb("{couleur}"), weight: "bold")[OK {ok}/{len(tirages)}]'
    else:
        tete = (f'#text(fill: rgb("{couleur}"), weight: "bold")[{ok}/{len(tirages)}] '
                f'#text(fill: rgb("{couleur}"), size: 7pt)[{typ(libelle)}]')
    tests = [r for r in tirages if r.get("total")]
    score = (f"{sum(r.get('passed', 0) for r in tests) / len(tests):.0f}"
             f"/{max(r['total'] for r in tests)} moy · " if tests else "")
    temps = duree(sum(r.get("wall_s", 0.0) for r in tirages) / len(tirages))
    return cel(tete + "#linebreak()" + gris(f"{score}{temps} moy"), teinte)


def cellule(r: dict | None) -> str:
    """`OK 12/12` puis, en gris, `45s · 3 tours` — le statut disant *pourquoi* si KO."""
    if r is None:
        return cel('#text(fill: luma(170))[—]')
    libelle, couleur, teinte, _ = STATUT.get(r.get("status", ""), INCONNU)
    tete = [f'#text(fill: rgb("{couleur}"), weight: "bold")[{typ(libelle)}]']
    if r.get("status") not in SANS_SCORE and r.get("total"):
        tete.append(f"{r.get('passed', 0)}/{r['total']}")
    pied = [duree(r.get("wall_s", 0.0))]
    if r.get("turns"):
        pied.append(tours(r["turns"]))
    return cel(" ".join(tete) + "#linebreak()" + gris(" · ".join(pied)), teinte)


# --------------------------------------------------------------------------- #
# Rendu
# --------------------------------------------------------------------------- #

def tableau(lignes: list[str], entetes: list[str], corps: list[list[str]],
            colonnes: str, alignement: str | None = None) -> None:
    """Un tableau Typst ; l'en-tête se répète en haut de chaque page enjambée."""
    lignes.append("#table(")
    lignes.append(f"  columns: ({colonnes}),")
    if alignement:
        lignes.append(f"  align: {alignement},")
    lignes.append("  table.header(" + ", ".join(entetes) + "),")
    for ligne in corps:
        lignes.append("  " + ", ".join(ligne) + ",")
    lignes.append(")")
    lignes.append("")


PREAMBULE = '''// Document engendré par recap.py — ne pas éditer à la main.
#set document(title: "Récapitulatif des runs", author: "bench.py")
#set page(
  paper: "a4",
  flipped: true,
  margin: (x: 1.1cm, top: 1.1cm, bottom: 1.0cm),
  // les tableaux enjambent les pages : un rappel du contexte évite de remonter
  header: context {
    let titres = query(selector(heading.where(level: 2)).before(here()))
    if counter(page).get().first() > 1 and titres.len() > 0 {
      align(right, text(size: 7pt, fill: luma(150))[#titres.last().body])
    }
  },
  footer: context align(center, text(size: 7pt, fill: luma(120))[
    #counter(page).display("1 / 1", both: true)
  ]),
)
#set text(size: 8.5pt, lang: "fr")
#set par(leading: 0.5em)
#set table(
  stroke: 0.4pt + luma(210),
  inset: (x: 5pt, y: 4.5pt),
  fill: (_, y) => if y == 0 { luma(236) },
)
// sans cela, une ligne coupée par un saut de page laisse sa moitié basse
// orpheline en haut de la suivante, sous l'en-tête répété
#set table.cell(breakable: false)
#show table.cell.where(y: 0): set text(size: 7.5pt, weight: "bold")
#show heading.where(level: 1): it => block(below: 0.8em)[#text(size: 16pt)[#it.body]]
#show heading.where(level: 2): it => block(above: 1.8em, below: 0.9em)[
  #text(size: 12pt)[#it.body]
  #v(-0.55em)
  #line(length: 100%, stroke: 0.6pt + luma(175))
]
#show heading.where(level: 3): it => block(above: 1.3em, below: 0.6em)[
  #text(size: 9.5pt, fill: luma(55))[#it.body]
]
'''


def agreger(mesures: list[dict]) -> dict:
    """Les cumuls d'un modèle. `taches` compte les tâches, `mesures` les tirages.

    Avec plusieurs graines, la réussite d'un modèle est la moyenne par tâche de
    sa part de tirages réussis — un pass@1 moyen, pas un décompte de tâches.
    """
    par_tache: dict = {}
    for r in mesures:
        par_tache.setdefault(r["task"], []).append(r)
    reussite = sum(sum(1 for r in v if r.get("status") == "pass") / len(v)
                   for v in par_tache.values())
    graines: dict = {}
    for r in mesures:
        graines.setdefault(r.get("seed", 0), []).append(r)
    par_graine = sorted(sum(1 for r in v if r.get("status") == "pass")
                        for v in graines.values())
    return {
        "taches": len(par_tache),
        "reussite": reussite,
        "graines": len(graines),
        "etendue": (par_graine[0], par_graine[-1]) if len(par_graine) > 1 else None,
        "mesures": len(mesures),
        "ok": sum(1 for r in mesures if r.get("status") == "pass"),
        "passes": sum(r.get("passed", 0) or 0 for r in mesures),
        "tests": sum(r.get("total", 0) or 0 for r in mesures),
        "temps": sum(r.get("wall_s", 0.0) or 0.0 for r in mesures),
        "tours": sum(r.get("turns", 0) or 0 for r in mesures),
        "tokens": sum(r.get("gen_tokens", 0) or 0 for r in mesures),
        "cout": sum(r.get("cost_usd", 0.0) or 0.0 for r in mesures),
    }


def classer(lot: dict[tuple, dict], modeles: list[str]) -> tuple[list[str], dict]:
    """Les modèles du meilleur au moins bon, avec leurs cumuls."""
    bilans = {m: agreger([r for r in lot.values() if r["model"] == m]) for m in modeles}
    ordre = sorted(modeles, key=lambda m: (
        -bilans[m]["reussite"] / (bilans[m]["taches"] or 1),   # pass@1 moyen
        -bilans[m]["passes"] / (bilans[m]["tests"] or 1),  # puis finesse des tests
        bilans[m]["temps"],                                # puis rapidité
        m,
    ))
    return ordre, bilans


def rendre_classement(out: list[str], lot: dict[tuple, dict], modeles: list[str],
                      bilans: dict, fiches: dict) -> None:
    """Un modèle par ligne : la vue qui répond à « lequel prendre ? »."""
    avec_tokens = any(bilans[m]["tokens"] for m in modeles)
    avec_cout = any(bilans[m]["cout"] for m in modeles)
    mesures = {m: [r for r in lot.values() if r["model"] == m] for m in modeles}

    # les deux chiffres qu'on veut sous les yeux en comparant : le reste des
    # poids est dans la section « Modèles mesurés »
    avec_fiches = any(fiches.get(m) for m in modeles)
    entetes = ["[\\#]", "[modèle]"]
    colonnes = ["auto", "1fr"]
    if avec_fiches:
        entetes += ["[paramètres]", "[quantisation]"]
        colonnes += ["auto", "auto"]
    entetes += ["[tâches réussies]", "[tests passés]", "[taux]",
                "[temps cumulé]", "[temps moyen]", "[tours]"]
    colonnes += ["auto", "auto", "auto", "auto", "auto", "auto"]
    # l'étendue entre graines : sans elle, un point d'écart au classement n'est
    # pas distinguable du bruit de tirage
    avec_etendue = any(bilans[m]["etendue"] for m in modeles)
    if avec_etendue:
        entetes.insert(entetes.index("[tests passés]"), "[étendue]")
        colonnes.insert(len(colonnes) - 5, "auto")
    if avec_tokens:
        entetes.append("[tokens générés]")
        colonnes.append("auto")
    if avec_cout:
        entetes.append("[coût]")
        colonnes.append("auto")
    entetes.append("[profil des statuts]")
    colonnes.append("auto")

    corps = []
    for rang, modele in enumerate(modeles, 1):
        b = bilans[modele]
        f = fiches.get(modele) or {}
        ligne = [
            cel(gris(str(rang), 8.0)),
            cel(mono(modele, coupable=True)),
        ]
        if avec_fiches:
            ligne.append(cel(typ(f.get("parameter_size") or "—")))
            ligne.append(cel(mono(f["quantization"]) if f.get("quantization") else "—"))
        reussies = (f'{b["reussite"]:.1f}/{b["taches"]}' if b["graines"] > 1
                    else f'{b["ok"]}/{b["taches"]}')
        ligne += [cel(reussies)]
        if avec_etendue:
            e = b["etendue"]
            ligne.append(cel(f'{e[0]}–{e[1]}' if e else "—"))
        ligne += [
            cel(f'{b["passes"]}/{b["tests"]}' if b["tests"] else "—"),
            cel(part(b["passes"], b["tests"])),
            cel(duree(b["temps"])),
            cel(duree(b["temps"] / b["mesures"]) if b["mesures"] else "—"),
            cel(entier(b["tours"])),
        ]
        if avec_tokens:
            ligne.append(cel(entier(b["tokens"])))
        if avec_cout:
            ligne.append(cel(f'{b["cout"]:.2f} \\$' if b["cout"] else "—"))
        ligne.append(cel(barre_empilee(mesures[modele])))
        corps.append(ligne)

    tableau(out, entetes, corps, ", ".join(colonnes),
            alignement="(x, y) => if x == 1 { left + horizon } else { right + horizon }")


def rendre_fiches(out: list[str], modeles: list[str], fiches: dict) -> None:
    """Les poids derrière les noms : quantisation, contexte natif, taille, empreinte."""
    if not any(fiches.get(m) for m in modeles):
        return
    out.append("=== Modèles mesurés")
    out.append("")

    corps = []
    for modele in modeles:
        f = fiches.get(modele) or {}
        defauts = " ".join(f"{cle} {valeur}" for cle, valeur in (f.get("defaults") or {}).items())
        corps.append([
            cel(mono(modele, coupable=True)),
            cel(typ(f.get("architecture") or f.get("family") or "—")),
            cel(typ(f.get("parameter_size") or "—")),
            cel(mono(f["quantization"]) if f.get("quantization") else "—"),
            cel(typ(f.get("format") or "—")),
            cel(contexte(f.get("context_length", 0))),
            cel(octets(f.get("size_bytes", 0))),
            cel(mono(f["digest"]) if f.get("digest") else "—"),
            cel(gris(typ(", ".join(f.get("capabilities") or [])) or "—", 7.5)),
            cel(gris(mono(defauts) if defauts else "—", 7.5)),
        ])
    entetes = ["[modèle]", "[archi]", "[paramètres]", "[quantisation]", "[format]",
               "[contexte natif]", "[taille]", "[empreinte]", "[capacités]",
               "[réglages du modelfile]"]
    tableau(out, entetes, corps, "auto, auto, auto, auto, auto, auto, auto, auto, auto, 1fr",
            alignement="(x, y) => if x == 0 or x >= 8 { left + horizon } "
                       "else { right + horizon }")
    out.append(gris("Relevé par `ollama show` (`/api/show`) : le nom d'un tag ne suffit pas "
                    "à identifier des poids, l'empreinte si. Les réglages du modelfile sont "
                    "ceux que le benchmark ne fixe pas lui-même.", 7.5))
    out.append("")


def rendre_detail(out: list[str], lot: dict[tuple, dict], modeles: list[str],
                  taches: list[str], par_tableau: int) -> None:
    """Une tâche par ligne, un modèle par colonne, par paquets de `par_tableau`."""
    par_cle: dict = {}
    for r in lot.values():
        par_cle.setdefault((r["model"], r["task"]), []).append(r)
    # un modèle « réussit » une tâche quand tous ses tirages passent
    reussites = {t: sum(1 for m in modeles
                        if par_cle.get((m, t))
                        and all(r.get("status") == "pass" for r in par_cle[(m, t)]))
                 for t in taches}

    for debut in range(0, len(modeles), par_tableau):
        paquet = modeles[debut:debut + par_tableau]
        fin = debut + len(paquet)
        if len(modeles) > par_tableau:
            out.append(gris(f"Modèles {debut + 1} à {fin} sur {len(modeles)}, "
                            f"dans l'ordre du classement.", 8.0))
            out.append("")

        corps, langue_courante = [], None
        for tache in taches:
            langue = tache.split("/")[0] if "/" in tache else "—"
            if langue != langue_courante:  # un intertitre par langage : le tableau
                langue_courante = langue   # est long, autant le baliser
                corps.append([cel(f'#text(weight: "bold", fill: luma(70))[{typ(langue)}]',
                                  fond="#f4f4f4", portee=len(paquet) + 1)])
            entete = (mono(tache.split("/", 1)[-1], coupable=True) + "#linebreak()"
                      + gris(f'{reussites[tache]}/{len(modeles)} modèles', 6.5))
            corps.append([cel(entete)]
                         + [cellule_groupe(par_cle[(m, tache)]) if (m, tache) in par_cle
                            else cellule(None) for m in paquet])

        entetes = ["[tâche]"] + [f"[{mono(m, coupable=True)}]" for m in paquet]
        tableau(out, entetes, corps, "3.1cm, " + ", ".join(["1fr"] * len(paquet)),
                alignement="left + horizon")


def recapitulatif(retenus: dict[tuple, dict], fiches: dict[tuple, dict], cache: dict,
                  mode: str, par_tableau: int) -> str:
    out = [PREAMBULE, "= Récapitulatif des runs", ""]
    if not retenus:
        out.append("_Aucun résultat._")
        return "\n".join(out) + "\n"

    engendre = datetime.now().strftime("%Y-%m-%d %H:%M")
    out.append(gris(f"Engendré le {engendre} · mode {typ(mode)} · "
                    f"{len(retenus)} mesures retenues", 8.0))
    out.append("")

    # une section par contexte de mesure : mélanger les machines ou les backends
    # dans un même tableau ferait comparer ce qui n'est pas comparable
    contextes = sorted({(r["_machine"], r["_host"], r["_backend"], r.get("_profil") or "")
                        for r in retenus.values()})
    for machine, host, backend, profil in contextes:
        lot = {k: r for k, r in retenus.items()
               if (r["_machine"], r["_host"], r["_backend"],
                   r.get("_profil") or "") == (machine, host, backend, profil)}
        taches = sorted({r["task"] for r in lot.values()})
        modeles, bilans = classer(lot, sorted({r["model"] for r in lot.values()}))

        # `machine` vaut « ?, ? RAM » quand bench.py n'a rien pu sonder : autant
        # titrer avec l'hôte, qui lui est toujours renseigné
        connue = machine.replace("?", "").replace("RAM", "").strip(" ,")
        lieu = machine if connue else host.split("://", 1)[-1].rstrip("/")
        # un profil agentique change le harnais, pas seulement le réglage : deux
        # profils dans un même tableau compareraient deux expériences
        titre_profil = {"cc": "profil Claude Code", "kilo": "profil kilocode",
                        "": "avant les profils"}.get(profil, f"profil {profil}")
        out.append(f"== {typ(backend)} — {typ(lieu)} · {typ(titre_profil)}")
        out.append("")
        graines = sorted({r.get("seed", 0) for r in lot.values()})
        tirages = (f" · graines {', '.join(str(g) for g in graines)}"
                   if len(graines) > 1 else "")
        out.append(gris(f"Hôte : {mono(host)} · mode {typ(mode)}{typ(tirages)} · "
                        f"{len(modeles)} modèle(s) · {len(taches)} tâche(s) · "
                        f"{len(lot)} mesure(s) retenue(s)", 8.0))
        out.append("")

        # la fiche ne dépend pas du profil : ce sont les mêmes poids des deux côtés
        fiches_lot = {m: (fiches.get((machine, host, backend, m))
                          or cache.get(host, {}).get(m) or {}) for m in modeles}

        out.append("=== Classement des modèles")
        out.append("")
        rendre_classement(out, lot, modeles, bilans, fiches_lot)
        rendre_fiches(out, modeles, fiches_lot)

        out.append("=== Détail tâche par tâche")
        out.append("")
        rendre_detail(out, lot, modeles, taches, par_tableau)

    out.append("=== Légende")
    out.append("")
    legende = ", ".join(
        f'#box(fill: rgb("{teinte}"), inset: (x: 3pt, y: 1.5pt), radius: 2pt, outset: (y: 1pt))'
        f'[#text(fill: rgb("{couleur}"), weight: "bold")[{typ(libelle)}]] {typ(explication)}'
        for libelle, couleur, teinte, explication in STATUT.values())
    out.append(f"#text(size: 7.5pt)[{legende}. Ces mêmes couleurs composent, dans cet "
               "ordre, le profil des statuts du classement.]")
    out.append("")
    out.append("#text(size: 7.5pt)[Chaque cellule est la mesure #strong[la plus récente] pour ce "
               "couple (modèle, tâche) sur cette machine, cet hôte, ce backend et ce profil, au "
               "format `statut · tests passés/total`, puis `temps mur · tours` en gris. "
               "Avec plusieurs graines, la cellule donne la part de tirages réussis "
               "(`2/3`) et les moyennes ; la colonne #strong[étendue] du classement donne "
               "le nombre de tâches réussies par la plus mauvaise et la meilleure graine — "
               "l'écart en deçà duquel un point de classement ne veut rien dire. Les modèles "
               "sont classés par part de tâches réussies, puis par part de tests passés, puis "
               "par temps cumulé.]")
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
    ap.add_argument("--mode", choices=MODES, default=MODE_DEFAUT,
                    help=f"mode rapporté (défaut : {MODE_DEFAUT})")
    ap.add_argument("--modeles-par-tableau", type=int, default=MODELES_PAR_TABLEAU,
                    metavar="N", help="colonnes de modèles par tableau de détail "
                                      f"(défaut : {MODELES_PAR_TABLEAU})")
    ap.add_argument("--sonder", action="store_true",
                    help="interroger les serveurs Ollama pour la fiche des modèles "
                         "qu'aucun run n'a consignée, et la garder dans runs/_modeles.json")
    ap.add_argument("--print", dest="afficher", action="store_true",
                    help="afficher la source Typst sur la sortie standard")
    ap.add_argument("--no-pdf", action="store_true", help="écrire le .typ sans compiler")
    args = ap.parse_args()

    if args.modeles_par_tableau < 1:
        sys.exit("--modeles-par-tableau doit valoir au moins 1")

    if args.runs:
        dossiers = [Path(a) if Path(a).is_dir() else RUNS / a for a in args.runs]
        manquants = [a for a, d in zip(args.runs, dossiers) if not d.is_dir()]
        if manquants:
            sys.exit("dossiers introuvables : " + ", ".join(manquants))
    elif RUNS.is_dir():
        dossiers = [d for d in RUNS.iterdir() if d.is_dir() and not d.name.startswith("_")]
    else:
        sys.exit(f"{RUNS} n'existe pas")

    retenus, fiches = collecter(dossiers)

    modeles = set(args.models.split(",")) if args.models else None
    taches = set(args.tasks.split(",")) if args.tasks else None
    filtres = {
        "_machine": lambda v: args.machine is None or args.machine.lower() in v.lower(),
        "_host": lambda v: args.host is None or args.host.lower() in v.lower(),
        "_backend": lambda v: args.backend is None or args.backend.lower() in v.lower(),
        "model": lambda v: modeles is None or v in modeles,
        "task": lambda v: taches is None or v in taches,
        "mode": lambda v: v == args.mode,
    }
    retenus = {k: r for k, r in retenus.items()
               if all(test(r.get(champ, "")) for champ, test in filtres.items())}

    cache = sonder(retenus, fiches) if args.sonder else lire_cache()
    texte = recapitulatif(retenus, fiches, cache, args.mode, args.modeles_par_tableau)

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
