# Tâche : cache LRU

Implémente dans `solution.py` un cache LRU (*Least Recently Used*) avec
exactement cette API publique :

```python
class LRUCache:
    def __init__(self, capacity: int) -> None: ...
    def get(self, key: int) -> int | None: ...
    def put(self, key: int, value: int) -> None: ...
    def __len__(self) -> int: ...
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
- `len(cache)` renvoie le nombre d'entrées présentes, toujours `<= capacity`.
- Une valeur peut valoir `0` : ne confonds pas « absente » et « fausse ».

## Exemple (LeetCode 146)

```python
c = LRUCache(2)
c.put(1, 1)
c.put(2, 2)
assert c.get(1) == 1   # 1 devient le plus récent
c.put(3, 3)            # évince la clé 2
assert c.get(2) is None
c.put(4, 4)            # évince la clé 1
assert c.get(1) is None
assert c.get(3) == 3
assert c.get(4) == 4
```

## Contraintes

- Bibliothèque standard uniquement (`collections.OrderedDict` est autorisé).
- Pas de bloc `if __name__ == "__main__"`, c'est un module importé.
