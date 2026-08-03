# Tâche : fréquence des mots (top-k)

Implémente dans `src/solution.c` :

```c
typedef struct {
    char  *word;   /* copie possédée, terminée par '\0' */
    size_t count;
} WordCount;

size_t word_freq(const char *text, size_t k, WordCount **out);
void   word_freq_free(WordCount *counts, size_t n);
```

`WordCount` doit porter exactement ces deux champs, sous ces noms et dans cet
ordre : la suite de tests cachée redéclare la structure à l'identique.

## `word_freq`

Écrit dans `*out` un tableau fraîchement alloué des `k` mots les plus fréquents
et renvoie le nombre d'éléments écrits.

- Un **mot** est une suite maximale de caractères ASCII alphanumériques
  (`A-Z`, `a-z`, `0-9`). Tout autre octet est un séparateur.
- Les mots sont normalisés en **minuscules ASCII** (`A-Z` → `a-z`, le reste est
  inchangé — pas de traitement Unicode, on travaille octet par octet).
- Le tableau est trié par **fréquence décroissante**, puis, à fréquence égale,
  par **ordre lexicographique croissant** du mot (`strcmp`, donc sur des octets
  non signés après minusculisation).
- Si le texte contient moins de `k` mots distincts, on renvoie tout ce qu'on a.
- Chaque `word` est une **copie possédée** par le tableau : le tableau doit
  survivre à la libération du texte d'origine.
- Cas où l'on renvoie `0` **et** met `*out` à `NULL` : `k == 0`, `text == NULL`,
  texte sans aucun mot. Aucune allocation ne doit fuir dans ces cas.

## `word_freq_free`

Libère les `n` mots puis le tableau lui-même. `word_freq_free(NULL, 0)` est
valide et ne fait rien. Après un appel à `word_freq`, exactement un appel à
`word_freq_free(tab, renvoyé)` doit tout rendre.

## Exemples

```c
WordCount *w;
size_t n = word_freq("the quick brown fox jumps over the lazy dog the fox", 3, &w);
/* n == 3, w == { {"the",3}, {"fox",2}, {"brown",1} } */
word_freq_free(w, n);

n = word_freq("Hello, hello! HELLO?", 5, &w);   /* n == 1, {"hello", 3} */
n = word_freq("", 3, &w);                       /* n == 0, w == NULL   */
```

Le troisième élément du premier exemple est `brown` et non `quick` : à fréquence
égale (1), c'est l'ordre lexicographique qui départage.

## Contraintes

- C11, **bibliothèque standard (libc) uniquement**, aucune autre bibliothèque.
- Pas de `main` : c'est une bibliothèque, le harnais de test fournit le `main`.
- La suite de tests cachée déclare elle-même les prototypes ci-dessus : respecte
  les noms et les types au caractère près.
- Compilation en `-Wall -Wextra -fsanitize=address,undefined` : la moindre
  erreur mémoire (débordement, lecture non initialisée, `free` invalide) ou le
  moindre comportement indéfini fait échouer le test.
