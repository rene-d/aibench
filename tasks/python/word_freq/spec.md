# Tâche : fréquence des mots (top-k)

Implémente dans `solution.py` la fonction suivante :

```python
def top_k(text: str, k: int) -> list[tuple[str, int]]: ...
```

## Règles

- Un **mot** est une suite maximale de caractères pour lesquels `ch.isalnum()`
  est vrai. Tout le reste est un séparateur.
- Les mots sont normalisés en minuscules avec `str.lower()` (minusculisation
  **Unicode**).
- Le résultat contient les `k` mots les plus fréquents, triés par **fréquence
  décroissante**, puis, à fréquence égale, par **ordre lexicographique croissant
  du mot** (comparaison naturelle des `str` Python).
- Si le texte contient moins de `k` mots distincts, on renvoie tout ce qu'on a.
- `k == 0` renvoie une liste vide.
- Chaque élément est un `tuple` `(mot, occurrences)`, pas une liste.

## Exemples

```python
t = "the quick brown fox jumps over the lazy dog the fox"
assert top_k(t, 3) == [("the", 3), ("fox", 2), ("brown", 1)]

assert top_k("Hello, hello! HELLO?", 5) == [("hello", 3)]
assert top_k("", 3) == []
```

## Contraintes

- Bibliothèque standard uniquement (`collections` est autorisé).
- Pas de bloc `if __name__ == "__main__"`, c'est un module importé.
