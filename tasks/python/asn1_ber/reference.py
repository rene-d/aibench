from dataclasses import dataclass


class BerError(Exception):
    pass


CLASSES = {0: "universal", 1: "application", 2: "context", 3: "private"}


@dataclass
class TLV:
    tag_class: str
    constructed: bool
    tag_number: int
    value: "bytes | list[TLV]"


def _read_identifier(data: bytes, i: int) -> tuple[str, bool, int, int]:
    if i >= len(data):
        raise BerError("identifiant tronqué")
    first = data[i]
    i += 1
    tag_class = CLASSES[(first & 0xC0) >> 6]
    constructed = bool(first & 0x20)
    number = first & 0x1F
    if number == 0x1F:
        number = 0
        while True:
            if i >= len(data):
                raise BerError("tag en forme longue tronqué")
            octet = data[i]
            i += 1
            number = (number << 7) | (octet & 0x7F)
            if not octet & 0x80:
                break
    return tag_class, constructed, number, i


def _read_length(data: bytes, i: int) -> tuple[int | None, int]:
    """Renvoie (longueur, position) ; longueur None signifie « indéfinie »."""
    if i >= len(data):
        raise BerError("longueur manquante")
    first = data[i]
    i += 1
    if first == 0x80:
        return None, i
    if first == 0xFF:
        raise BerError("octet de longueur 0xFF réservé")
    if first < 0x80:
        return first, i
    count = first & 0x7F
    if i + count > len(data):
        raise BerError("octets de longueur tronqués")
    return int.from_bytes(data[i:i + count], "big"), i + count


def _parse(data: bytes, i: int) -> tuple[TLV, int]:
    tag_class, constructed, number, i = _read_identifier(data, i)
    length, i = _read_length(data, i)

    if length is None:
        if not constructed:
            raise BerError("longueur indéfinie interdite sur un type primitif")
        children: list[TLV] = []
        while True:
            if i + 1 >= len(data):
                raise BerError("longueur indéfinie non close par 00 00")
            if data[i] == 0x00 and data[i + 1] == 0x00:
                return TLV(tag_class, constructed, number, children), i + 2
            child, i = _parse(data, i)
            children.append(child)

    end = i + length
    if end > len(data):
        raise BerError("contenu tronqué")
    if not constructed:
        return TLV(tag_class, constructed, number, data[i:end]), end

    children = []
    while i < end:
        child, i = _parse(data, i)
        children.append(child)
    if i != end:
        raise BerError("un enfant dépasse le contenu de son parent")
    return TLV(tag_class, constructed, number, children), end


def decode(data: bytes) -> TLV:
    if not data:
        raise BerError("entrée vide")
    tlv, i = _parse(bytes(data), 0)
    if i != len(data):
        raise BerError(f"{len(data) - i} octet(s) en trop après le TLV")
    return tlv


def decode_integer(value: bytes) -> int:
    if not value:
        raise BerError("INTEGER vide")
    return int.from_bytes(bytes(value), "big", signed=True)


def decode_oid(value: bytes) -> str:
    if not value:
        raise BerError("OID vide")
    subids, current, pending = [], 0, False
    for octet in bytes(value):
        current = (current << 7) | (octet & 0x7F)
        pending = True
        if not octet & 0x80:
            subids.append(current)
            current, pending = 0, False
    if pending:
        raise BerError("dernier sous-identifiant inachevé")

    first = subids[0]
    if first < 80:
        arcs = [first // 40, first % 40]
    else:
        arcs = [2, first - 80]
    arcs.extend(subids[1:])
    return ".".join(str(a) for a in arcs)
