# Tâche : décodeur de PDU ASN.1 en BER

Implémente dans `src/solution.c` un décodeur *Basic Encoding Rules*
(ITU-T X.690) capable d'analyser une PDU complète, y compris les formes que les
décodeurs naïfs ratent : tag long, longueur longue, longueur indéfinie.

## API exacte

```c
typedef enum {
    BER_OK = 0,
    BER_EMPTY,                 /* entrée vide */
    BER_TRUNCATED,             /* données tronquées */
    BER_TRAILING,              /* octets en trop après le TLV de premier niveau */
    BER_INDEFINITE_PRIMITIVE,  /* longueur indéfinie sur un type primitif */
    BER_RESERVED_LENGTH,       /* octet de longueur 0xFF */
    BER_UNTERMINATED,          /* longueur indéfinie jamais close par 00 00 */
    BER_OVERFLOW,              /* tag, longueur ou entier trop grand */
    BER_INVALID,               /* contenu INTEGER ou OID mal formé */
    BER_NOMEM                  /* échec d'allocation */
} BerError;

typedef enum {
    BER_UNIVERSAL   = 0,
    BER_APPLICATION = 1,
    BER_CONTEXT     = 2,
    BER_PRIVATE     = 3
} BerClass;

typedef struct BerTlv {
    BerClass             tag_class;
    int                  constructed;   /* 0 ou 1 */
    unsigned long        tag_number;
    const unsigned char *value;         /* primitif : pointe DANS data */
    size_t               value_len;
    struct BerTlv      **children;      /* construit : child_count pointeurs */
    size_t               child_count;
} BerTlv;

BerError ber_decode(const unsigned char *data, size_t len, BerTlv **out);
void     ber_free(BerTlv *tlv);
BerError ber_decode_integer(const unsigned char *value, size_t len, long long *out);
BerError ber_decode_oid(const unsigned char *value, size_t len, char **out);
```

`BerTlv` doit porter exactement ces sept champs, sous ces noms et dans cet ordre :
la suite de tests cachée redéclare la structure à l'identique et lit ses champs
directement.

## `ber_decode`

Analyse **exactement un** TLV et le range dans `*out`. En cas d'erreur, met
`*out` à `NULL`, renvoie le code correspondant et **ne laisse rien fuir**.

- Type **primitif** : `value` pointe **dans `data`** (à l'octet de contenu, sans
  aucune copie), `value_len` est la longueur du contenu, `children` vaut `NULL`
  et `child_count` vaut `0`. Un contenu de longueur nulle donne
  `value_len == 0` ; `value` peut alors valoir n'importe quel pointeur dans
  `data`, il n'est pas déréférencé.
- Type **construit** : `children` est un tableau de `child_count` pointeurs vers
  les TLV enfants décodés récursivement, dans l'ordre ; `value` vaut `NULL` et
  `value_len` vaut `0`.

L'arbre entier appartient à l'appelant, qui le rend d'un seul appel à
`ber_free`. Le tampon `data`, lui, appartient toujours à l'appelant : le
décodeur ne le copie pas, donc l'arbre ne doit pas lui survivre.

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

Un numéro de tag qui ne tient pas dans un `unsigned long` → `BER_OVERFLOW`.

## Octet(s) de longueur

- `< 0x80` : forme courte, c'est la longueur.
- `== 0x80` : **longueur indéfinie**. Le contenu est une suite de TLV terminée
  par l'*end-of-contents* `00 00`. Réservé aux types **construits**.
- `== 0xFF` : valeur réservée → `BER_RESERVED_LENGTH`.
- sinon : forme longue. Les 7 bits de poids faible donnent le **nombre d'octets
  de longueur** qui suivent, gros-boutiste. Plus de 8 octets → `BER_OVERFLOW`.

Exemple : `04 81 C8` → OCTET STRING de 200 octets. `04 82 01 00` → 256 octets.

## `ber_decode_integer`

Décode les octets de contenu d'un INTEGER : gros-boutiste, **complément à deux
signé**. Contenu vide → `BER_INVALID`. Plus de 8 octets → `BER_OVERFLOW`.
La valeur décodée n'est écrite dans `*out` qu'en cas de succès : en cas
d'erreur, `*out` n'est pas modifié.

```c
ber_decode_integer((const unsigned char *)"\x7f", 1, &v);          /*  127 */
ber_decode_integer((const unsigned char *)"\x00\x80", 2, &v);      /*  128 */
ber_decode_integer((const unsigned char *)"\x80", 1, &v);          /* -128 */
ber_decode_integer((const unsigned char *)"\xff\x7f", 2, &v);      /* -129 */
```

## `ber_decode_oid`

Décode les octets de contenu d'un OBJECT IDENTIFIER en chaîne pointée
fraîchement allouée (`malloc`), que l'appelant libère avec `free()`.

- Les sous-identifiants sont codés en base 128, bit 8 = continuation.
- Le **premier** octet encode deux arcs : soit `v = 40×X + Y`. Si `v < 80` alors
  `X = v / 40` et `Y = v % 40` ; **sinon `X = 2` et `Y = v - 80`** (le second
  arc n'est pas borné quand `X` vaut 2).
- Contenu vide, ou dernier octet avec le bit de continuation encore à 1 →
  `BER_INVALID`.
- Sous-identifiant qui ne tient pas dans un `unsigned long` → `BER_OVERFLOW`.
- En cas d'erreur, `*out` est mis à `NULL`.

```c
ber_decode_oid((const unsigned char *)"\x2a\x86\x48\x86\xf7\x0d", 6, &s);
/* s == "1.2.840.113549" */
ber_decode_oid((const unsigned char *)"\x55\x04\x03", 3, &s);   /* "2.5.4.3" */
ber_decode_oid((const unsigned char *)"\x81\x34", 2, &s);       /* "2.100"   */
```

## Erreurs de `ber_decode`

| situation | code |
|---|---|
| `data == NULL` ou `len == 0` | `BER_EMPTY` |
| longueur annoncée plus grande que ce qui reste, octets de longueur longue manquants, forme longue de tag interrompue | `BER_TRUNCATED` |
| octets en trop après le TLV de premier niveau | `BER_TRAILING` |
| longueur indéfinie sur un type primitif | `BER_INDEFINITE_PRIMITIVE` |
| octet de longueur `0xFF` | `BER_RESERVED_LENGTH` |
| longueur indéfinie jamais close par `00 00` | `BER_UNTERMINATED` |
| numéro de tag ou compte d'octets de longueur trop grand | `BER_OVERFLOW` |

Les octets sont examinés de gauche à droite : c'est la **première** anomalie
rencontrée qui donne le code.

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

- C11, **bibliothèque standard (libc) uniquement**. N'utilise **aucune
  bibliothèque ASN.1** : écris le décodeur.
- Pas de `main` : c'est une bibliothèque, le harnais de test fournit le `main`.
- La suite de tests cachée déclare elle-même les types et prototypes ci-dessus :
  respecte les noms, l'ordre et les types au caractère près.
- Compilation en `-Wall -Wextra -fsanitize=address,undefined` : la moindre
  erreur mémoire (débordement, lecture non initialisée, `free` invalide) ou le
  moindre comportement indéfini fait échouer le test.
