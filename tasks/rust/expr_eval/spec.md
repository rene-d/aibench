# Tâche : évaluateur d'expressions arithmétiques

Implémente dans `src/lib.rs` d'une crate nommée `task` un analyseur syntaxique
descendant récursif et son évaluateur :

```rust
#[derive(Debug, PartialEq)]
pub enum EvalError {
    UnexpectedChar(char),
    UnexpectedEnd,
    UnbalancedParen,
    DivisionByZero,
}

pub fn eval(expr: &str) -> Result<f64, EvalError>;
```

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
- `%` est l'opérateur `%` de Rust sur `f64` (le signe suit celui du dividende :
  `-7 % 3 == -1`).
- `^` est l'exponentiation (`f64::powf`).

## Erreurs — règles exactes

| situation | erreur |
|---|---|
| l'entrée se termine alors qu'une opérande est attendue (`""`, `"2+"`, `"-"`) | `UnexpectedEnd` |
| caractère inconnu du lexeur (`"2 & 3"`) | `UnexpectedChar('&')` |
| jeton inattendu là où une opérande est attendue (`"1 + * 2"`) | `UnexpectedChar('*')` — le caractère du jeton fautif |
| `(` jamais refermée (`"(1+2"`) | `UnbalancedParen` |
| `)` en trop à la fin (`"1+2)"`) | `UnbalancedParen` |
| division ou modulo par `0.0` exactement (`"1/0"`, `"1%0"`) | `DivisionByZero` |

L'évaluation se fait de gauche à droite au fil de l'analyse.

## Exemples

```rust
assert_eq!(eval("2+3*4"), Ok(14.0));
assert_eq!(eval("(2+3)*4"), Ok(20.0));
assert_eq!(eval("2^3^2"), Ok(512.0));
assert_eq!(eval("-2^2"), Ok(-4.0));
assert_eq!(eval("1/0"), Err(EvalError::DivisionByZero));
assert_eq!(eval("(1+2"), Err(EvalError::UnbalancedParen));
```

## Contraintes

- Pas de dépendance externe (uniquement la bibliothèque standard).
- Pas de `unsafe`, pas de `fn main`.
- Édition 2021.
