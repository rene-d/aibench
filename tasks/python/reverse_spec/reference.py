import json
import re
from collections import defaultdict

BLANCS = re.compile(r"[\s\u00a0]")


def _montant(valeur):
    if isinstance(valeur, str):
        return float(BLANCS.sub("", valeur).replace(",", "."))
    return float(valeur)


def rendu(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        ventes = json.load(f)

    par_region = defaultdict(lambda: [0, 0.0])
    for vente in ventes:
        if vente.get("annule"):
            continue
        region = vente["region"].strip().upper()
        par_region[region][0] += 1
        par_region[region][1] += _montant(vente["montant"])

    lignes = ["region;commandes;total"]
    total_n = 0
    total_montant = 0.0
    for region, (n, montant) in sorted(par_region.items(), key=lambda kv: (-kv[1][1], kv[0])):
        lignes.append(f"{region};{n};{montant:.2f}")
        total_n += n
        total_montant += montant
    lignes.append(f"TOTAL;{total_n};{total_montant:.2f}")
    return "\n".join(lignes) + "\n"
