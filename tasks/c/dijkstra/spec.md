# Tâche : plus courts chemins (Dijkstra)

Implémente dans `src/solution.c` un graphe orienté pondéré et l'algorithme de
Dijkstra :

```c
#include <limits.h>   /* LLONG_MAX */
#include <stdint.h>   /* SIZE_MAX  */

typedef struct Graph Graph;   /* type opaque, contenu libre */

Graph *graph_new(size_t n);
void   graph_free(Graph *g);
int    graph_add_edge(Graph *g, size_t u, size_t v, long long w);
size_t graph_order(const Graph *g);

int    dijkstra(const Graph *g, size_t src, long long *dist, size_t *prev);
size_t dijkstra_path(const Graph *g, size_t src, size_t dst,
                     size_t *out, size_t out_cap);
```

La structure `Graph` reste **opaque** : la suite de tests ne connaît que le nom
du type et ne manipule que des pointeurs.

## Le graphe

| fonction | contrat |
|---|---|
| `graph_new(n)` | graphe de `n` sommets numérotés `0..n-1`, sans arête. `n == 0` est valide. Échec d'allocation → `NULL`. |
| `graph_free(g)` | libère tout. `graph_free(NULL)` est valide. |
| `graph_order(g)` | nombre de sommets. `graph_order(NULL)` → `0`. |
| `graph_add_edge(g, u, v, w)` | ajoute l'arête **orientée** `u → v` de poids `w`. `0` en cas de succès, `-1` en cas de refus. |

`graph_add_edge` refuse, **sans rien modifier**, et renvoie `-1` si : `g` est
`NULL`, `u >= n`, `v >= n`, ou `w <= 0`. Les poids sont donc strictement
positifs — ce qui rend le départage ci-dessous déterministe.

Les arêtes multiples entre les deux mêmes sommets sont autorisées (c'est la plus
légère qui compte) et les boucles `u → u` aussi.

## `dijkstra`

Calcule les plus courts chemins depuis `src`. Renvoie `0` en cas de succès,
`-1` si `g` est `NULL`, si `src >= n`, si `dist` est `NULL` ou si une allocation
échoue.

- `dist[i]` : longueur du plus court chemin `src → i`, `LLONG_MAX` si `i` est
  inatteignable. `dist[src] == 0`.
- `prev` peut être `NULL` (on ne le remplit alors pas). Sinon `prev[i]` reçoit
  le prédécesseur de `i` sur ce plus court chemin, et `SIZE_MAX` si `i` est
  inatteignable **ou si `i == src`**.
- **Départage** : si plusieurs prédécesseurs donnent la même distance minimale,
  `prev[i]` est le **plus petit indice** parmi eux. Le résultat ne doit donc pas
  dépendre de l'ordre d'insertion des arêtes ni de l'ordre de la file.

Les deux tableaux font `graph_order(g)` éléments et appartiennent à l'appelant.

## `dijkstra_path`

Renvoie la longueur, **en nombre de sommets**, du plus court chemin `src → dst`
départagé comme ci-dessus, et `0` si `dst` est inatteignable, si `g` est `NULL`,
si `src >= n`, si `dst >= n`, ou si une allocation échoue.

- Le chemin est écrit dans `out` **de `src` à `dst`**, `out[0] == src` et
  `out[L-1] == dst`.
- `src == dst` donne `L == 1`.
- Si `out` est `NULL` ou si `out_cap < L`, la fonction renvoie quand même `L`
  mais **n'écrit rien du tout** (pas d'écriture partielle).

## Complexité

`dijkstra` doit tourner en **O((V + E) log V)** : file de priorité (tas
binaire), pas de balayage linéaire des sommets restants à chaque étape. Un test
construit un graphe de 50 000 sommets et 150 000 arêtes et échoue au-delà de
5 secondes.

## Exemple

```c
Graph *g = graph_new(5);
graph_add_edge(g, 0, 1, 4);
graph_add_edge(g, 0, 2, 1);
graph_add_edge(g, 2, 1, 2);
graph_add_edge(g, 1, 3, 1);
graph_add_edge(g, 2, 3, 5);
/* le sommet 4 reste isolé */

long long dist[5];
size_t prev[5];
dijkstra(g, 0, dist, prev);
/* dist = {0, 3, 1, 4, LLONG_MAX} */
/* prev = {SIZE_MAX, 2, 0, 1, SIZE_MAX} */

size_t path[5];
size_t len = dijkstra_path(g, 0, 3, path, 5);   /* len == 4, path = {0, 2, 1, 3} */
graph_free(g);
```

## Contraintes

- C11, **bibliothèque standard (libc) uniquement**, aucune autre bibliothèque.
- Pas de `main` : c'est une bibliothèque, le harnais de test fournit le `main`.
- La suite de tests cachée déclare elle-même les prototypes ci-dessus : respecte
  les noms et les types au caractère près.
- Compilation en `-Wall -Wextra -fsanitize=address,undefined` : la moindre
  erreur mémoire (débordement, lecture non initialisée, `free` invalide) ou le
  moindre comportement indéfini fait échouer le test.
