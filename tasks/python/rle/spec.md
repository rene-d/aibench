# Tâche : Run-Length Encoding (RLE)

Implémente dans `solution.py` les deux fonctions suivantes :

```python
def encode(text: str) -> str: ...
def decode(text: str) -> str: ...
```

## Règles

- `encode` compresse les séquences de caractères identiques consécutifs en
  `<nombre><caractère>`. **Une séquence de longueur 1 ne porte pas de nombre.**
- `decode` est l'inverse exact de `encode` : `decode(encode(s)) == s` pour toute
  chaîne `s` ne contenant pas de chiffre.
- Les données d'entrée de `encode` ne contiennent jamais de chiffre, mais peuvent
  contenir des espaces et des lettres majuscules/minuscules.
- La chaîne vide est encodée et décodée en chaîne vide.
- Les compteurs peuvent avoir plusieurs chiffres (ex : `12W`).

## Exemples

| entrée | `encode` |
|---|---|
| `""` | `""` |
| `"XYZ"` | `"XYZ"` |
| `"AABBBCCCC"` | `"2A3B4C"` |
| `"  hsqq qww  "` | `"2 hs2q q2w2 "` |

`decode("12WB12W3B24WB")` vaut `"WWWWWWWWWWWWBWWWWWWWWWWWWBBBWWWWWWWWWWWWWWWWWWWWWWWWB"`.

## Contraintes

- Bibliothèque standard uniquement.
- Pas de bloc `if __name__ == "__main__"`, c'est un module importé.
