"""Trois règles du contrat, prises au mot."""

import unicodedata
from decimal import Decimal, ROUND_HALF_UP


def arrondi(x: float, n: int = 0) -> float:
    """Arrondi au plus proche, les milieux exacts s'éloignant de zéro."""
    quantum = Decimal(1).scaleb(-n)
    return float(Decimal(x).quantize(quantum, rounding=ROUND_HALF_UP))


def fusion(base: dict, patch: dict) -> dict:
    """`None` dans le patch veut dire « ne touche pas », pas « efface »."""
    sortie = dict(base)
    for cle, valeur in patch.items():
        if valeur is not None:
            sortie[cle] = valeur
    return sortie


def cle_tri(nom: str) -> tuple[str, str]:
    """(nom plié pour le tri, nom d'origine pour départager)."""
    plie = " ".join(nom.split())
    plie = unicodedata.normalize("NFD", plie)
    plie = "".join(c for c in plie if not unicodedata.combining(c))
    return plie.lower(), nom
