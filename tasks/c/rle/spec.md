# Tâche : Run-Length Encoding (RLE)

Implémente dans `src/solution.c` les deux fonctions suivantes :

```c
char *rle_encode(const char *input);
char *rle_decode(const char *input);
```

Les deux renvoient une chaîne **fraîchement allouée** (`malloc`), terminée par
`'\0'`, que l'appelant libère avec `free()`. La chaîne vide en entrée donne une
chaîne vide allouée, **pas** `NULL`.

## `rle_encode`

- Compresse les suites de caractères identiques consécutifs en
  `<nombre><caractère>`. **Une suite de longueur 1 ne porte pas de nombre.**
- Les compteurs peuvent avoir plusieurs chiffres (`12W`).
- L'entrée ne contient jamais de chiffre, mais peut contenir des espaces et des
  majuscules comme des minuscules. Les octets sont traités tels quels, un par un
  (pas d'UTF-8 à interpréter).
- `input == NULL` → `NULL`.

| entrée | sortie |
|---|---|
| `""` | `""` |
| `"XYZ"` | `"XYZ"` |
| `"AABBBCCCC"` | `"2A3B4C"` |
| `"  hsqq qww  "` | `"2 hs2q q2w2 "` |

## `rle_decode`

Inverse exact de `rle_encode` : `rle_decode(rle_encode(s))` redonne `s` pour
toute chaîne `s` sans chiffre.

```c
rle_decode("12WB12W3B24WB")
/* → "WWWWWWWWWWWWBWWWWWWWWWWWWBBBWWWWWWWWWWWWWWWWWWWWWWWWB" */
```

Renvoie `NULL`, sans rien allouer, si l'entrée est mal formée :

- `input == NULL` ;
- un compteur en fin de chaîne, sans caractère derrière (`"3"`, `"AB12"`) ;
- un compteur commençant par `'0'` (`"0A"`, `"03A"`) — `rle_encode` n'en produit
  jamais ;
- un compteur supérieur à `1000000`.

## Contraintes

- C11, **bibliothèque standard (libc) uniquement**, aucune autre bibliothèque.
- Pas de `main` : c'est une bibliothèque, le harnais de test fournit le `main`.
- La suite de tests cachée déclare elle-même les prototypes ci-dessus : respecte
  les noms et les types au caractère près.
- Compilation en `-Wall -Wextra -fsanitize=address,undefined` : la moindre
  erreur mémoire (débordement, lecture non initialisée, `free` invalide) ou le
  moindre comportement indéfini fait échouer le test.
