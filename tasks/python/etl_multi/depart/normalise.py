"""Normalisation des lignes brutes. Fourni avec l'énoncé, complet et correct."""

NIVEAUX = ("DEBUG", "INFO", "WARN", "ERROR")


def normalise_ligne(ligne: str) -> dict | None:
    """`<horodatage>|<service>|<niveau>|<durée ms>|<message>` → dict, ou None.

    Renvoie None pour une ligne vide, un commentaire (`#`), un nombre de champs
    incorrect, un niveau inconnu ou une durée qui n'est pas un entier positif.
    """
    ligne = ligne.strip()
    if not ligne or ligne.startswith("#"):
        return None
    champs = ligne.split("|")
    if len(champs) != 5:
        return None
    horodatage, service, niveau, duree, message = (c.strip() for c in champs)
    niveau = niveau.upper()
    if not service or niveau not in NIVEAUX:
        return None
    if not duree.isdigit():
        return None
    if "T" not in horodatage:
        return None
    return {
        "date": horodatage.split("T", 1)[0],
        "service": service,
        "niveau": niveau,
        "duree_ms": int(duree),
        "message": message,
    }
