# Tâche : rapport de commandes à partir d'un JSON

Le projet contient `data/commandes.json` : un tableau JSON d'enregistrements de
commandes, **exporté d'un système réel, donc sale**. Implémente dans
`solution.py` :

```python
def report(path: str) -> dict: ...
```

`path` est le chemin d'un fichier au même format que `data/commandes.json`.
**Lis ce fichier avant d'écrire ton code** : la spécification ci-dessous dit
quels problèmes existent, elle ne dit pas sous quelles formes ils apparaissent.
C'est le fichier qui te l'apprend, et la suite de tests utilise exactement les
mêmes conventions d'écriture.

## Champs d'un enregistrement

`id`, `client`, `categorie`, `montant`, `devise`, `date`. Un champ peut être
absent de l'objet, valoir `null`, ou être une chaîne vide.

## Validité

Un enregistrement est **ignoré** si l'un de ces contrôles échoue :

- `id` absent ou `null` ;
- `client` absent, `null`, ou vide une fois les espaces de bord retirés ;
- `montant` ne représente pas un nombre. **Le fichier écrit les montants de
  plusieurs façons** : ce sont tantôt des nombres JSON, tantôt du texte suivant
  diverses conventions (séparateur décimal, séparateur de milliers). Un montant
  peut être nul ou négatif, ce qui est valide ;
- `devise` : seul l'euro est retenu, et **le fichier écrit l'euro de plusieurs
  façons** (casse comprise). Une `devise` absente vaut euro. Toute autre devise
  fait ignorer l'enregistrement ;
- `date` illisible. **Le fichier mélange plusieurs formats de date** ; une date
  syntaxiquement bien formée mais qui ne correspond à aucun jour réel est
  illisible.

Ensuite seulement vient la **déduplication** : les enregistrements valides sont
parcourus dans l'ordre du fichier, et si un `id` a déjà été retenu, l'occurrence
suivante est un doublon — elle est écartée, elle n'est pas « ignorée ».

## Normalisation

- `client` et `categorie` : espaces de bord retirés, minuscules.
- `categorie` absente, `null` ou vide : `"inconnue"`.
- `date` : réduite au mois, sous la forme `"AAAA-MM"`.
- Tout `total` est arrondi avec `round(total, 2)`, **une seule fois, à la fin**,
  sur la somme — pas sur chaque montant.

## Valeur de retour

```python
{
    "n_commandes": int,   # enregistrements retenus (hors ignorés et doublons)
    "n_ignorees": int,
    "n_doublons": int,
    "par_client": {"acme": {"n": 4, "total": 1263.1}, ...},
    "par_mois":   {"2026-01": {"n": 4, "total": 1259.1}, ...},
    "top_categories": [("pro", 9), ...],
}
```

- `par_client` et `par_mois` : un sous-dictionnaire `{"n": ..., "total": ...}`
  par clé, uniquement pour les clés qui ont au moins une commande retenue.
- `top_categories` : au plus **3** entrées, triées par nombre d'occurrences
  décroissant puis, à égalité, par nom croissant. Chaque entrée est un `tuple`
  `(categorie, n)`, pas une liste.

## Contraintes

- Bibliothèque standard uniquement (`json`, `datetime`, `collections`, `re`…).
- Pas de bloc `if __name__ == "__main__"`, c'est un module importé.
- N'écris pas en dur les résultats de `data/commandes.json` : les tests
  appellent `report` sur d'autres fichiers.
