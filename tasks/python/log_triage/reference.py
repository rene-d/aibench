import re
from datetime import datetime, timezone

NIVEAUX = {"ERROR", "FATAL", "WARN", "WARNING", "INFO", "DEBUG", "TRACE"}
ERREURS = {"ERROR", "FATAL"}

CHIFFRES = re.compile(r"\d+")
ISO = re.compile(r"^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})(?:[.,]\d+)?Z?\s+(.*)$")
FR = re.compile(r"^(\d{2})/(\d{2})/(\d{4}) (\d{2}:\d{2}:\d{2})\s+(.*)$")
EPOCH = re.compile(r"^\[(\d{9,11})\]\s+(.*)$")
NIVEAU = re.compile(r"^\[?([A-Za-z]+)\]?[\s:]\s*(.*)$")


def _horodatage(ligne):
    """(datetime UTC, reste de la ligne), ou None si la ligne n'est pas une en-tête."""
    m = ISO.match(ligne)
    if m:
        return _date(f"{m.group(1)} {m.group(2)}", "%Y-%m-%d %H:%M:%S", m.group(3))
    m = FR.match(ligne)
    if m:
        return _date(f"{m.group(3)}-{m.group(2)}-{m.group(1)} {m.group(4)}",
                     "%Y-%m-%d %H:%M:%S", m.group(5))
    m = EPOCH.match(ligne)
    if m:
        return datetime.fromtimestamp(int(m.group(1)), timezone.utc), m.group(2)
    return None


def _date(texte, fmt, reste):
    try:
        return datetime.strptime(texte, fmt).replace(tzinfo=timezone.utc), reste
    except ValueError:
        return None


def _niveau(reste):
    """(niveau, message), ou None si le premier mot n'est pas un niveau connu."""
    m = NIVEAU.match(reste)
    if not m:
        return None
    niveau = m.group(1).upper()
    return (niveau, m.group(2).strip()) if niveau in NIVEAUX else None


def triage(path: str) -> list:
    with open(path, encoding="utf-8", errors="replace") as f:
        lignes = f.read().splitlines()

    entrees = []  # [horodatage, niveau, message, a_des_suites]
    courante = None
    for ligne in lignes:
        entete = _horodatage(ligne)
        if entete is None:
            # ligne de continuation : elle appartient à l'entrée précédente, s'il
            # y en a une qui a été retenue
            if courante is not None and ligne.strip():
                courante[3] = True
            continue
        quand, reste = entete
        niveau = _niveau(reste)
        if niveau is None:
            courante = None
            continue
        courante = [quand, niveau[0], niveau[1], False]
        entrees.append(courante)

    groupes = {}
    for quand, niveau, message, suites in entrees:
        if niveau not in ERREURS or not message:
            continue
        signature = CHIFFRES.sub("N", message)
        g = groupes.setdefault(signature, {"signature": signature, "n": 0, "first": quand,
                                           "last": quand, "traceback": False})
        g["n"] += 1
        g["first"] = min(g["first"], quand)
        g["last"] = max(g["last"], quand)
        g["traceback"] = g["traceback"] or suites

    for g in groupes.values():
        g["first"] = g["first"].strftime("%Y-%m-%dT%H:%M:%SZ")
        g["last"] = g["last"].strftime("%Y-%m-%dT%H:%M:%SZ")
    return sorted(groupes.values(), key=lambda g: (-g["n"], g["signature"]))
