# Tâche : fréquence des mots (top-k)

Implémente dans `src/lib.rs` d'une crate nommée `task` la fonction publique suivante :

```rust
pub fn top_k(text: &str, k: usize) -> Vec<(String, usize)>
```

## Règles

- Un **mot** est une suite maximale de caractères pour lesquels
  `char::is_alphanumeric()` est vrai. Tout le reste est un séparateur.
- Les mots sont normalisés en minuscules avec `str::to_lowercase()`
  (minusculisation **Unicode**, pas `to_ascii_lowercase`).
- Le résultat contient les `k` mots les plus fréquents, triés par **fréquence
  décroissante**, puis, à fréquence égale, par **ordre lexicographique croissant
  du mot** (ordre naturel des `String` en Rust).
- Si le texte contient moins de `k` mots distincts, on renvoie tout ce qu'on a.
- `k == 0` renvoie un vecteur vide.

## Exemples

```rust
let t = "the quick brown fox jumps over the lazy dog the fox";
assert_eq!(
    top_k(t, 3),
    vec![
        ("the".to_string(), 3),
        ("fox".to_string(), 2),
        ("brown".to_string(), 1),
    ]
);

assert_eq!(top_k("Hello, hello! HELLO?", 5), vec![("hello".to_string(), 3)]);
assert_eq!(top_k("", 3), vec![]);
```

## Contraintes

- Pas de dépendance externe (uniquement la bibliothèque standard).
- Pas de `fn main`, c'est une bibliothèque.
- Édition 2021.
