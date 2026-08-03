# Tâche : triage d'un journal applicatif

Le projet contient `data/app.log` : le journal d'une application qui a changé de
bibliothèque de log deux fois dans sa vie, **donc dont les lignes ne sont pas
toutes au même format**. Implémente dans `solution.py` :

```python
def triage(path: str) -> list: ...
```

`path` est le chemin d'un journal au même format que `data/app.log`.
**Lis ce fichier avant d'écrire ton code** : la spécification dit ce qu'il faut
faire, pas à quoi ressemblent les lignes. C'est le fichier qui te l'apprend, et
la suite de tests utilise exactement les mêmes formats.

## Découpage en entrées

Une ligne qui commence par un **horodatage** ouvre une nouvelle entrée. Toute
autre ligne non vide est la **suite** de l'entrée ouverte (trace d'exception,
message multi-lignes) et lui appartient. Les lignes qui précèdent le premier
horodatage n'appartiennent à personne.

`data/app.log` mélange **plusieurs écritures de l'horodatage**, dont une qui
n'est pas lisible par un humain. Toutes désignent un instant en UTC ; une
fraction de seconde, quand il y en a une, est tronquée.

## Sélection

Après l'horodatage vient le **niveau**, puis le message. Le niveau peut être
écrit dans n'importe quelle casse et peut être entouré de crochets. Les niveaux
existants sont `ERROR`, `FATAL`, `WARN`, `WARNING`, `INFO`, `DEBUG` et `TRACE`.

- Seuls `ERROR` et `FATAL` sont retenus.
- Si le premier mot après l'horodatage n'est aucun de ces niveaux, l'entrée est
  abandonnée — **ainsi que ses lignes de suite**.
- Une entrée dont le message est vide est abandonnée.

## Regroupement

La **signature** d'une entrée est son message dans lequel chaque suite maximale
de chiffres est remplacée par un `N` unique — c'est ce qui rassemble deux
occurrences du même incident dont seuls les identifiants diffèrent.

Les entrées retenues sont regroupées par signature. Pour chaque groupe :

```python
{
    "signature": "db: timeout after Ns (conn=N)",
    "n": 4,                            # nombre d'occurrences
    "first": "2026-01-04T08:12:03Z",   # occurrence la plus ancienne
    "last": "2026-01-04T08:26:30Z",    # occurrence la plus récente
    "traceback": True,                 # au moins une occurrence a des lignes de suite
}
```

- `first` et `last` sont les instants **chronologiques** minimum et maximum du
  groupe, au format `"%Y-%m-%dT%H:%M:%SZ"`. Le journal n'est pas trié : l'ordre
  des lignes n'est pas l'ordre du temps.
- La liste renvoyée contient **tous** les groupes, triés par `n` décroissant
  puis, à égalité, par `signature` croissante.

## Contraintes

- Bibliothèque standard uniquement (`re`, `datetime`, `collections`…).
- Pas de bloc `if __name__ == "__main__"`, c'est un module importé.
- N'écris pas en dur les résultats de `data/app.log` : les tests appellent
  `triage` sur d'autres journaux.
