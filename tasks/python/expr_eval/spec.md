# Tâche : évaluateur d'expressions arithmétiques

Implémente dans `solution.py` un analyseur syntaxique descendant récursif et son
évaluateur :

```python
class EvalError(Exception): ...
class UnexpectedChar(EvalError):
    char: str          # le caractère fautif, accessible en attribut
class UnexpectedEnd(EvalError): ...
class UnbalancedParen(EvalError): ...
class DivisionByZero(EvalError): ...

def eval_expr(expr: str) -> float: ...
```

Les quatre exceptions dérivent de `EvalError`. `UnexpectedChar` expose le
caractère fautif via l'attribut `.char` (une chaîne d'un caractère).

## Grammaire (à respecter exactement)

```
expr    := term (('+' | '-') term)*
term    := unary (('*' | '/' | '%') unary)*
unary   := '-' unary | power
power   := atom ('^' unary)?
atom    := nombre | '(' expr ')'
```

Conséquences à ne pas rater :

- `+ - * / %` sont **associatifs à gauche** : `10-3-2 == 5`, `100/5/2 == 10`.
- `^` est **associatif à droite** : `2^3^2 == 512` (et non 64).
- L'unaire moins lie **moins fort** que `^` : `-2^2 == -4` (et non 4).
- L'exposant peut être unaire : `2^-1 == 0.5`.
- L'unaire moins est répétable : `--5 == 5`.

## Lexique

- Un **nombre** est `chiffre+ ('.' chiffre+)?`. Donc `3` et `2.75` sont valides,
  `.5` et `3.` ne le sont pas.
- Les espaces et tabulations sont ignorés partout.
- `%` est l'opérateur `%` de **Python** sur les flottants : le résultat prend le
  signe du diviseur, donc `-7 % 3 == 2`.
- `^` est l'exponentiation (`**`).
- `eval_expr` renvoie toujours un `float`.

## Erreurs — règles exactes

| situation | exception |
|---|---|
| l'entrée se termine alors qu'une opérande est attendue (`""`, `"2+"`, `"-"`) | `UnexpectedEnd` |
| caractère inconnu du lexeur (`"2 & 3"`) | `UnexpectedChar` avec `.char == "&"` |
| jeton inattendu là où une opérande est attendue (`"1 + * 2"`) | `UnexpectedChar` avec `.char == "*"` |
| `(` jamais refermée (`"(1+2"`) | `UnbalancedParen` |
| `)` en trop à la fin (`"1+2)"`) | `UnbalancedParen` |
| division ou modulo par `0.0` exactement (`"1/0"`, `"1%0"`) | `DivisionByZero` |

L'évaluation se fait de gauche à droite au fil de l'analyse.

## Exemples

```python
assert eval_expr("2+3*4") == 14.0
assert eval_expr("(2+3)*4") == 20.0
assert eval_expr("2^3^2") == 512.0
assert eval_expr("-2^2") == -4.0
```

## Contraintes

- Bibliothèque standard uniquement. **N'utilise pas `eval()` ni `ast.literal_eval`** :
  écris le parseur.
- Pas de bloc `if __name__ == "__main__"`, c'est un module importé.
