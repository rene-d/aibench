# Tâche : cache LRU

Implémente dans `src/lib.rs` d'une crate nommée `task` un cache LRU
(*Least Recently Used*) avec exactement cette API publique :

```rust
pub struct LruCache { /* champs privés au choix */ }

impl LruCache {
    pub fn new(capacity: usize) -> Self;
    pub fn get(&mut self, key: i32) -> Option<i32>;
    pub fn put(&mut self, key: i32, value: i32);
    pub fn len(&self) -> usize;
    pub fn is_empty(&self) -> bool;
}
```

## Règles

- `capacity >= 1` (on ne teste pas `capacity == 0`).
- `get(key)` renvoie la valeur si la clé est présente et **marque la clé comme la
  plus récemment utilisée**. Sinon `None`, sans effet de bord.
- `put(key, value)` insère ou met à jour la clé et la marque comme la plus
  récemment utilisée. Si l'insertion dépasse la capacité, on évince la clé la
  **moins récemment utilisée**.
- Mettre à jour une clé existante ne fait jamais grossir le cache et n'évince
  jamais rien.
- `len()` renvoie le nombre d'entrées présentes, toujours `<= capacity`.

## Exemple (LeetCode 146)

```rust
let mut c = LruCache::new(2);
c.put(1, 1);
c.put(2, 2);
assert_eq!(c.get(1), Some(1)); // 1 devient le plus récent
c.put(3, 3);                   // évince la clé 2
assert_eq!(c.get(2), None);
c.put(4, 4);                   // évince la clé 1
assert_eq!(c.get(1), None);
assert_eq!(c.get(3), Some(3));
assert_eq!(c.get(4), Some(4));
```

## Contraintes

- Pas de dépendance externe (uniquement la bibliothèque standard).
- Pas de `unsafe`.
- Pas de `fn main`, c'est une bibliothèque.
- Édition 2021.
