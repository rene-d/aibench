# Tâche : réparer un tampon circulaire

`src/solution.c` **existe déjà et contient des bugs**. Ta mission n'est pas de
réécrire le fichier de zéro, mais de le réparer : trouve les défauts, corrige-les,
et fais passer les tests.

Le test `tests/visible.c` est fourni avec l'énoncé. Il fait partie du contrat :
**ne le modifie pas**, fais-le passer.

## API

```c
struct ring;   /* type opaque, défini dans src/solution.c */

struct ring *ring_new(size_t capacity);
void         ring_free(struct ring *r);
int          ring_push(struct ring *r, int value);
int          ring_pop(struct ring *r, int *out);
size_t       ring_len(const struct ring *r);
size_t       ring_capacity(const struct ring *r);
```

## Règles

- `ring_new(capacity)` réserve un tampon de `capacity` entiers et renvoie `NULL`
  si `capacity` vaut 0 ou si l'allocation échoue.
- `ring_free(NULL)` est autorisé et ne fait rien.
- `ring_push` ajoute en queue : `0` en cas de succès, `-1` si le tampon est plein.
- `ring_pop` retire en tête, écrit la valeur dans `*out` si `out` n'est pas
  `NULL` : `0` en cas de succès, `-1` si le tampon est vide.
- `ring_len` renvoie le nombre d'éléments présents, `ring_capacity` la capacité
  totale. Les deux renvoient 0 pour un pointeur `NULL`.
- L'ordre est strictement FIFO, **y compris après plusieurs tours de tampon** :
  c'est là que le code fourni se trompe.
- Aucune fuite mémoire, aucun accès hors bornes : le projet est compilé avec
  `-fsanitize=address,undefined`.
