# Tâche : rapport d'activité, réparti sur trois fichiers

Le projet contient déjà deux modules. **Lis-les avant d'écrire quoi que ce soit**,
l'énoncé ne répète pas leurs signatures :

- `normalise.py` — fourni, complet et correct. Ne le modifie pas sans raison.
- `agrege.py` — fourni, mais `agrege()` n'est **pas implémentée** : elle lève
  `NotImplementedError`. C'est à toi de l'écrire, **dans ce fichier**.

Puis implémente dans `solution.py` :

```python
def rapport(lignes: list[str]) -> str: ...
```

`rapport` doit **réutiliser** `normalise.normalise_ligne` et `agrege.agrege` :
ne recopie pas leur logique dans `solution.py`, les deux modules sont testés
séparément.

## Ce que fait `agrege(enregs)`

Elle reçoit la liste des enregistrements produits par `normalise_ligne` (jamais
`None`) et renvoie un dictionnaire `{service: stats}` où `stats` vaut :

```python
{"total": int, "erreurs": int, "duree_totale": int, "duree_max": int}
```

- `total` : nombre d'enregistrements du service.
- `erreurs` : nombre d'enregistrements dont le niveau vaut `"ERROR"`.
- `duree_totale` : somme des `duree_ms`.
- `duree_max` : plus grande `duree_ms` du service (0 si le service n'a aucun
  enregistrement, ce qui ne peut pas arriver).
- Un service absent de l'entrée est absent du résultat. L'entrée vide donne `{}`.

## Ce que fait `rapport(lignes)`

1. normalise chaque ligne, en écartant celles que `normalise_ligne` rejette ;
2. agrège le reste ;
3. rend une ligne de texte par service, dans l'ordre **erreurs décroissantes,
   puis nom du service croissant**, au format exact :

```
<service> : <total> lignes, <erreurs> erreurs, <moyenne> ms en moyenne, max <duree_max> ms
```

- `<moyenne>` est la division **entière** de `duree_totale` par `total`.
- Les lignes sont jointes par `"\n"`, sans saut de ligne final.
- Une entrée sans aucune ligne exploitable rend la chaîne vide.

## Exemple

```python
lignes = [
    "2026-02-03T10:15:00Z|api|INFO|120|ok",
    "2026-02-03T10:15:01Z|api|ERROR|300|boum",
    "2026-02-03T10:15:02Z|db|INFO|40|ok",
    "# commentaire",
]
rapport(lignes)
# "api : 2 lignes, 1 erreurs, 210 ms en moyenne, max 300 ms\n"
# "db : 1 lignes, 0 erreurs, 40 ms en moyenne, max 40 ms"
```
