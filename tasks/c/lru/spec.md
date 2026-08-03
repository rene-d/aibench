# Tâche : cache LRU

Implémente dans `src/solution.c` un cache *Least Recently Used* avec exactement
cette API :

```c
typedef struct LruCache LruCache;   /* type opaque, contenu libre */

LruCache *lru_new(size_t capacity);
void      lru_free(LruCache *c);
int       lru_get(LruCache *c, int key, int *out_value);
int       lru_put(LruCache *c, int key, int value);
size_t    lru_len(const LruCache *c);
size_t    lru_keys(const LruCache *c, int *out, size_t out_cap);
```

La structure `LruCache` reste **opaque** : la suite de tests ne connaît que le
nom du type et ne manipule que des pointeurs.

## Sémantique

| fonction | contrat |
|---|---|
| `lru_new(capacity)` | cache vide de capacité `capacity`. `capacity == 0` → `NULL`. Échec d'allocation → `NULL`. |
| `lru_free(c)` | libère tout. `lru_free(NULL)` est valide et ne fait rien. |
| `lru_get(c, key, out)` | `1` si la clé est présente, `0` sinon. Si présente et `out != NULL`, écrit la valeur dans `*out`. |
| `lru_put(c, key, value)` | insère ou met à jour. `0` en cas de succès, `-1` si une allocation échoue (le cache reste alors intact et utilisable). |
| `lru_len(c)` | nombre d'entrées, toujours `<= capacity`. `lru_len(NULL)` → `0`. |
| `lru_keys(c, out, out_cap)` | écrit les clés **de la plus récemment utilisée à la moins récemment utilisée**, au plus `out_cap`, et renvoie le nombre écrit. |

## Récence

- `lru_get` sur une clé présente la marque comme la plus récemment utilisée,
  **même si `out_value` vaut `NULL`**.
- `lru_get` sur une clé absente ne modifie rien.
- `lru_put` marque la clé comme la plus récemment utilisée, qu'elle soit
  nouvelle ou déjà là.
- Mettre à jour une clé existante ne fait jamais grossir le cache et n'évince
  jamais rien.
- Quand une insertion dépasse la capacité, on évince la clé la **moins**
  récemment utilisée, et une seule.

`lru_keys` rend cet ordre observable : après `put(1,·) put(2,·) get(1,·)`, il
écrit `{1, 2}`.

## Complexité

`lru_get` et `lru_put` doivent être en **O(1) amorti** : table de hachage pour
retrouver l'entrée, liste doublement chaînée pour l'ordre de récence. Un test
enchaîne 200 000 opérations sur un cache de 20 000 entrées et échoue au bout de
10 secondes : un parcours linéaire à chaque opération ne passe pas.

## Exemple (LeetCode 146)

```c
LruCache *c = lru_new(2);
int v;
lru_put(c, 1, 1);
lru_put(c, 2, 2);
lru_get(c, 1, &v);       /* 1, v == 1 ; la clé 1 devient la plus récente */
lru_put(c, 3, 3);        /* évince la clé 2 */
lru_get(c, 2, &v);       /* 0 */
lru_put(c, 4, 4);        /* évince la clé 1 */
lru_get(c, 1, &v);       /* 0 */
lru_get(c, 3, &v);       /* 1, v == 3 */
lru_get(c, 4, &v);       /* 1, v == 4 */
lru_free(c);
```

Attention : la valeur `0` est une valeur comme une autre. C'est le **code de
retour** qui dit si la clé est là, jamais la valeur écrite.

## Contraintes

- C11, **bibliothèque standard (libc) uniquement**, aucune autre bibliothèque.
- Pas de `main` : c'est une bibliothèque, le harnais de test fournit le `main`.
- La suite de tests cachée déclare elle-même les prototypes ci-dessus : respecte
  les noms et les types au caractère près.
- Compilation en `-Wall -Wextra -fsanitize=address,undefined` : la moindre
  erreur mémoire (débordement, lecture non initialisée, `free` invalide) ou le
  moindre comportement indéfini fait échouer le test.
