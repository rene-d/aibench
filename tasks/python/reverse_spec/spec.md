# Tâche : reproduire un rapport dont personne n'a la spécification

Le service qui produisait ce rapport a disparu, et sa documentation avec. Il
reste deux fichiers dans `data/` :

- `ventes.json` — une entrée du service ;
- `rapport_attendu.txt` — **la sortie que le service a produite pour cette
  entrée exacte**.

Implémente dans `solution.py` :

```python
def rendu(path: str) -> str: ...
```

`rendu(path)` doit renvoyer, **caractère pour caractère**, ce que le service
aurait produit pour le fichier de ventes situé à `path` — donc
`rendu("data/ventes.json")` doit être exactement le contenu de
`data/rapport_attendu.txt`.

## Ce qu'on te donne, et ce qu'on ne te donne pas

Aucune règle ne t'est fournie : ni les filtres, ni les regroupements, ni le tri,
ni les conversions, ni le formatage des nombres. **Tout est déductible en
comparant les deux fichiers**, à condition de les lire l'un contre l'autre au
lieu de deviner.

Quelques questions qui valent la peine d'être posées au fichier :

- combien d'enregistrements l'entrée contient-elle, et combien la sortie en
  compte-t-elle ? Si les nombres ne tombent pas juste, quel champ explique
  l'écart ?
- deux lignes d'entrée qui se ressemblent finissent-elles au même endroit dans
  la sortie ? Qu'a-t-il fallu leur faire subir pour cela ?
- dans quel ordre les lignes de sortie apparaissent-elles ? Et quand ce critère
  ne départage pas deux lignes, qu'est-ce qui les départage ?
- les montants de l'entrée ne sont pas tous écrits pareil. La sortie, si.

La suite de tests cachée appelle `rendu` sur **d'autres** fichiers de ventes,
au même format et suivant les mêmes règles. Reproduire la sortie fournie sans
avoir compris les règles ne rapporte qu'un seul test.

## Contraintes

- Bibliothèque standard uniquement (`json`, `collections`…).
- Pas de bloc `if __name__ == "__main__"`, c'est un module importé.
