"""Agrégation par service — version de référence."""


def agrege(enregs: list[dict]) -> dict:
    stats: dict = {}
    for e in enregs:
        s = stats.setdefault(e["service"], {"total": 0, "erreurs": 0,
                                            "duree_totale": 0, "duree_max": 0})
        s["total"] += 1
        s["erreurs"] += e["niveau"] == "ERROR"
        s["duree_totale"] += e["duree_ms"]
        s["duree_max"] = max(s["duree_max"], e["duree_ms"])
    return stats
