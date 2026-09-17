"""Rapport d'activité : orchestre les deux modules fournis."""

from agrege import agrege
from normalise import normalise_ligne


def rapport(lignes: list[str]) -> str:
    enregs = [e for e in (normalise_ligne(l) for l in lignes) if e is not None]
    stats = agrege(enregs)
    ordonnes = sorted(stats.items(), key=lambda kv: (-kv[1]["erreurs"], kv[0]))
    return "\n".join(
        f"{service} : {s['total']} lignes, {s['erreurs']} erreurs, "
        f"{s['duree_totale'] // s['total']} ms en moyenne, max {s['duree_max']} ms"
        for service, s in ordonnes
    )
