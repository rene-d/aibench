# Tâche : trois règles contre-intuitives, un contrat à respecter

Implémente dans `solution.py` :

```python
def arrondi(x: float, n: int = 0) -> float: ...
def fusion(base: dict, patch: dict) -> dict: ...
def cle_tri(nom: str) -> tuple[str, str]: ...
```

Le fichier `test_contrat.py` est fourni avec l'énoncé. **Il fait partie du
contrat et ne doit pas être modifié** : il dit la vérité sur ce qui est attendu,
y compris là où ça surprend. Si un de ses tests échoue, c'est ton code qui a
tort — même quand il a l'air d'avoir raison.

## `arrondi(x, n=0)`

Arrondit `x` au multiple de `10**-n` le plus proche. **En cas d'égalité exacte,
on s'éloigne de zéro** : `arrondi(2.5) == 3.0`, `arrondi(-2.5) == -3.0`,
`arrondi(0.125, 2) == 0.13`.

Ce n'est **pas** le comportement de `round()`, qui arrondit les milieux vers le
nombre pair (`round(2.5) == 2`, `round(0.125, 2) == 0.12`). Les valeurs à mi-chemin
s'entendent sur la valeur binaire exacte du flottant reçu.

## `fusion(base, patch)`

Renvoie un **nouveau** dictionnaire :

- une clé de `patch` écrase celle de `base` ;
- **sauf si sa valeur est `None`** : `None` veut dire « ne touche pas », la
  valeur de `base` est conservée ;
- une clé présente seulement dans `patch` et valant `None` n'apparaît pas dans
  le résultat ;
- `base` et `patch` ne sont pas modifiés.

## `cle_tri(nom)`

Renvoie `(plié, nom)` où `plié` est `nom` :

1. débarrassé des espaces de début et de fin, ses suites d'espaces internes
   réduites à un seul espace ;
2. dépouillé de ses accents (`é` → `e`, `Ç` → `C`…) ;
3. mis en minuscules.

Le second élément est le `nom` d'origine, inchangé : il départage deux noms qui
se plient pareil, et rend le tri déterministe.
