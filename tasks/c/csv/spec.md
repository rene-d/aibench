# Tâche : analyseur CSV (RFC 4180)

Implémente dans `src/solution.c` un analyseur CSV strict :

```c
typedef enum {
    CSV_OK = 0,
    CSV_UNTERMINATED_QUOTE,  /* champ cité jamais refermé */
    CSV_BARE_QUOTE,          /* guillemet interdit hors d'un champ cité */
    CSV_NOMEM                /* échec d'allocation */
} CsvError;

typedef struct {
    char ***rows;    /* rows[i][j] : champ j de la ligne i, terminé par '\0' */
    size_t  *ncols;  /* ncols[i] : nombre de champs de la ligne i */
    size_t   nrows;
} CsvTable;

CsvError csv_parse(const char *input, CsvTable **out);
void     csv_free(CsvTable *t);
```

`CsvTable` doit porter exactement ces trois champs, sous ces noms et dans cet
ordre : la suite de tests cachée redéclare la structure à l'identique.

## `csv_parse`

En cas de succès, alloue une `CsvTable`, la range dans `*out` et renvoie
`CSV_OK`. En cas d'erreur, met `*out` à `NULL`, renvoie le code d'erreur et **ne
laisse rien fuir** : tout ce qui a déjà été alloué doit être libéré.

Chaque ligne a son propre nombre de champs : les lignes de largeurs différentes
sont acceptées telles quelles, sans remplissage.

### Découpage

- Le séparateur de champ est la virgule.
- Le séparateur de ligne est `\n` ou `\r\n`. Un `\r` **qui n'est pas suivi d'un
  `\n`** est un caractère ordinaire du champ.
- Un saut de ligne **final** ne crée pas de ligne vide supplémentaire :
  `"a,b\n"` donne une ligne, `"a,b"` aussi.
- Une ligne vide au milieu donne une ligne d'**un seul champ vide** :
  `"a\n\nb"` donne trois lignes.
- Les champs vides sont conservés : `"a,,b"` donne trois champs, dont un vide.
- Une entrée vide (`""`) ou `NULL` donne une table valide avec `nrows == 0`
  (et non `NULL`).

### Champs cités

Un champ est cité si son **premier** caractère est un guillemet.

- Entre les guillemets, la virgule, `\n`, `\r` et les espaces sont littéraux.
- `""` à l'intérieur représente un guillemet littéral : `"a""b"` → `a"b`.
- Le guillemet fermant doit être immédiatement suivi d'une virgule, d'une fin de
  ligne ou de la fin de l'entrée. Sinon → `CSV_BARE_QUOTE` (`"ab"c` est refusé).
- Un guillemet ouvrant jamais refermé → `CSV_UNTERMINATED_QUOTE`.
- Un guillemet **à l'intérieur** d'un champ non cité → `CSV_BARE_QUOTE`
  (`a"b` est refusé). Les espaces comptent : `a, "b"` a un champ non cité qui
  commence par une espace, donc il est refusé.

### Exemples

| entrée | résultat |
|---|---|
| `""` | 0 ligne |
| `"a"` | 1 ligne, 1 champ : `a` |
| `"a,b,c"` | 1 ligne, 3 champs |
| `"a,b\nc,d\n"` | 2 lignes de 2 champs |
| `"a,,b"` | `a`, ``, `b` |
| `",\n"` | 1 ligne, 2 champs vides |
| `"\"x,y\",z"` | 2 champs : `x,y` et `z` |
| `"\"ligne1\nligne2\""` | 1 ligne, 1 champ contenant un `\n` |
| `"\"a\"\"b\""` | 1 champ : `a"b` |
| `a,"b` (guillemet jamais refermé) | `CSV_UNTERMINATED_QUOTE` |
| `a"b` (guillemet dans un champ non cité) | `CSV_BARE_QUOTE` |
| `"ab"c` (texte après le guillemet fermant) | `CSV_BARE_QUOTE` |

## `csv_free`

Libère les champs, les tableaux de champs, `rows`, `ncols` et la table.
`csv_free(NULL)` est valide et ne fait rien.

## Contraintes

- C11, **bibliothèque standard (libc) uniquement**, aucune autre bibliothèque.
- Pas de `main` : c'est une bibliothèque, le harnais de test fournit le `main`.
- La suite de tests cachée déclare elle-même les prototypes ci-dessus : respecte
  les noms et les types au caractère près.
- Compilation en `-Wall -Wextra -fsanitize=address,undefined` : la moindre
  erreur mémoire (débordement, lecture non initialisée, `free` invalide) ou le
  moindre comportement indéfini fait échouer le test.
