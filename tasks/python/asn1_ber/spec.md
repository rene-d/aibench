# Tâche : décodeur de PDU ASN.1 en BER

Implémente dans `solution.py` un décodeur *Basic Encoding Rules* (ITU-T X.690)
capable d'analyser une PDU complète, y compris les formes que les décodeurs
naïfs ratent : tag long, longueur longue, longueur indéfinie.

## API exacte

```python
class BerError(Exception): ...

class TLV:
    tag_class: str            # "universal" | "application" | "context" | "private"
    constructed: bool
    tag_number: int
    value: bytes | list["TLV"]   # bytes si primitif, liste d'enfants si construit

def decode(data: bytes) -> TLV: ...
def decode_integer(value: bytes) -> int: ...
def decode_oid(value: bytes) -> str: ...
```

`TLV` doit exposer ces quatre attributs sous ces noms exacts (un
`@dataclass` fait très bien l'affaire). `decode` analyse **exactement un** TLV et
lève `BerError` s'il reste des octets après lui.

## Octet d'identification

| bits | rôle |
|---|---|
| 8-7 (`0xC0`) | classe : `00` universal, `01` application, `10` context, `11` private |
| 6 (`0x20`) | 1 = construit, 0 = primitif |
| 5-1 (`0x1F`) | numéro de tag |

Si les bits 5-1 valent tous 1 (soit 31), le numéro de tag est en **forme
longue** : il suit sur un ou plusieurs octets, bit 8 = « il y en a d'autres »,
bits 7-1 = données, gros-boutiste en base 128.

Exemple : `9F 81 00` → classe context, primitif, tag `1×128 + 0` = **128**.

## Octet(s) de longueur

- `< 0x80` : forme courte, c'est la longueur.
- `== 0x80` : **longueur indéfinie**. Le contenu est une suite de TLV terminée
  par l'*end-of-contents* `00 00`. Réservé aux types **construits**.
- `== 0xFF` : valeur réservée → `BerError`.
- sinon : forme longue. Les 7 bits de poids faible donnent le **nombre d'octets
  de longueur** qui suivent, gros-boutiste.

Exemple : `04 81 C8` → OCTET STRING de 200 octets. `04 82 01 00` → 256 octets.

## Contenu

- Type **primitif** → `value` est un `bytes` (les octets bruts du contenu).
- Type **construit** → `value` est la `list` des TLV enfants, décodés
  récursivement, dans l'ordre.

## `decode_integer(value)`

Décode les octets de contenu d'un INTEGER : gros-boutiste, **complément à deux
signé**. Contenu vide → `BerError`.

```python
decode_integer(b"\x7f")      ==  127
decode_integer(b"\x00\x80")  ==  128
decode_integer(b"\x80")      == -128
decode_integer(b"\xff\x7f")  == -129
```

## `decode_oid(value)`

Décode les octets de contenu d'un OBJECT IDENTIFIER en chaîne pointée.

- Les sous-identifiants sont codés en base 128, bit 8 = continuation.
- Le **premier** octet encode deux arcs : soit `v = 40×X + Y`. Si `v < 80` alors
  `X = v // 40` et `Y = v % 40` ; **sinon `X = 2` et `Y = v - 80`** (le second
  arc n'est pas borné quand `X` vaut 2).
- Contenu vide, ou dernier octet avec le bit de continuation encore à 1 →
  `BerError`.

```python
decode_oid(b"\x2a\x86\x48\x86\xf7\x0d") == "1.2.840.113549"
decode_oid(b"\x55\x04\x03")             == "2.5.4.3"
decode_oid(b"\x81\x34")                 == "2.100"
```

## Erreurs — toutes des `BerError`

- entrée vide ;
- données tronquées (longueur annoncée plus grande que ce qui reste, octets de
  longueur longue manquants, forme longue de tag interrompue) ;
- octets en trop après le TLV de premier niveau ;
- longueur indéfinie sur un type **primitif** ;
- octet de longueur `0xFF` ;
- longueur indéfinie jamais close par `00 00`.

## Exemple complet — PDU SNMP GetRequest

```
30 26                                SEQUENCE
   02 01 00                          version = 0
   04 06 70 75 62 6C 69 63           community = "public"
   A0 19                             [0] construit = GetRequest
      02 04 12 34 56 78              request-id = 305419896
      02 01 00                       error-status = 0
      02 01 00                       error-index = 0
      30 0B                          varbind-list
         30 09                       varbind
            06 05 2B 06 01 02 01     OID 1.3.6.1.2.1
            05 00                    NULL
```

## Contraintes

- Bibliothèque standard uniquement. **N'utilise aucune bibliothèque ASN.1** :
  écris le décodeur.
- Pas de bloc `if __name__ == "__main__"`, c'est un module importé.
