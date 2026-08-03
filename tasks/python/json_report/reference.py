import json
import re
from collections import defaultdict
from datetime import datetime

EURO = {"EUR", "€"}
BLANCS = re.compile(r"[\s\u00a0]")
FORMATS = ("%Y-%m-%d", "%d/%m/%Y")


def _montant(valeur):
    """float, ou None si la valeur ne représente pas un nombre."""
    if valeur is None or isinstance(valeur, bool):
        return None
    if isinstance(valeur, (int, float)):
        return float(valeur)
    if not isinstance(valeur, str):
        return None
    txt = BLANCS.sub("", valeur).replace(",", ".")
    if not txt:
        return None
    try:
        return float(txt)
    except ValueError:
        return None


def _mois(valeur):
    """'AAAA-MM', ou None si la date n'est reconnue par aucun format."""
    if not isinstance(valeur, str) or not valeur.strip():
        return None
    txt = valeur.strip()[:10]
    for fmt in FORMATS:
        try:
            d = datetime.strptime(txt, fmt).date()
        except ValueError:
            continue
        return f"{d.year:04d}-{d.month:02d}"
    return None


def _texte(valeur):
    return valeur.strip().lower() if isinstance(valeur, str) else ""


def report(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        enregistrements = json.load(f)

    n_ignorees = n_doublons = 0
    vus = set()
    par_client = defaultdict(lambda: [0, 0.0])
    par_mois = defaultdict(lambda: [0, 0.0])
    categories = defaultdict(int)

    for rec in enregistrements:
        ident = rec.get("id")
        client = _texte(rec.get("client"))
        montant = _montant(rec.get("montant"))
        devise = rec.get("devise", "EUR")
        devise = devise.strip().upper() if isinstance(devise, str) else ""
        mois = _mois(rec.get("date"))

        if (ident is None or not client or montant is None
                or devise not in EURO or mois is None):
            n_ignorees += 1
            continue
        if ident in vus:
            n_doublons += 1
            continue
        vus.add(ident)

        categories[_texte(rec.get("categorie")) or "inconnue"] += 1
        for seau, cle in ((par_client, client), (par_mois, mois)):
            seau[cle][0] += 1
            seau[cle][1] += montant

    plier = lambda seau: {k: {"n": v[0], "total": round(v[1], 2)} for k, v in seau.items()}
    return {
        "n_commandes": len(vus),
        "n_ignorees": n_ignorees,
        "n_doublons": n_doublons,
        "par_client": plier(par_client),
        "par_mois": plier(par_mois),
        "top_categories": sorted(categories.items(), key=lambda kv: (-kv[1], kv[0]))[:3],
    }
