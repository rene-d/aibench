# bench — évaluation d'un LLM sur du code Rust, Python et C

Harnais d'évaluation qui fait écrire du code à un modèle (local via Ollama,
n'importe quel fournisseur via LiteLLM, ou Claude via le CLI) et note le résultat
avec une **suite de tests cachée** que le modèle ne voit jamais. Trois langages,
deux modes, 15 tâches, 284 tests.

## Installation

Rien à installer côté harnais : Python 3 (bibliothèque standard uniquement),
`cargo` pour la série Rust, `cmake` et un compilateur C (clang ou gcc) pour la
série C. Puis, selon le backend visé, un Ollama qui tourne, un proxy LiteLLM
joignable, ou le CLI `claude`.

## Utilisation

```bash
# 1. vérifier que les tests cachés sont justes (les solutions de référence doivent passer 100 %)
python3 bench.py --self-test

# 2. évaluer un modèle sur tout le benchmark (15 tâches × 2 modes)
python3 bench.py --models qwen3.6:35b-a3b-coding-mxfp8

# 3. comparer plusieurs modèles, restreindre les tâches, les langages ou les modes
python3 bench.py --models gemma4:31b-mlx,qwen3.6:35b-mlx --tasks rle,lru --modes direct
python3 bench.py --models qwen3.6:35b-mlx --lang c

# 4. comparer un modèle local à Claude via le CLI Claude Code (auth abonnement)
python3 bench.py --models qwen3.6:35b-a3b-coding-mxfp8,claude:opus

# 5. passer par un proxy LiteLLM (n'importe quel fournisseur qu'il route)
python3 bench.py --models litellm:gpt-4o-mini,litellm:claude-sonnet-5 \
                 --litellm-base-url http://localhost:4000
```

| préfixe | backend |
|---|---|
| *(aucun)* ou `ollama:` | modèle **Ollama** local, API native |
| `litellm:` | endpoint **OpenAI-compatible** : proxy LiteLLM, ou tout `/v1/chat/completions` |
| `claude:` | **CLI Claude Code** (`claude:opus`, `claude:sonnet`, `claude:claude-opus-5`) |

`--backend litellm` change le backend des noms sans préfixe, pour ne pas préfixer
toute une liste.

Sélection des tâches : `--lang rust`, `--lang python` ou `--lang c` pour une
série entière, `--tasks` pour un sous-ensemble (`rle` prend les trois langages,
`python/asn1_ber` une seule tâche).

## Les trois langages

Tout ce qui diffère entre un projet cargo, un projet Python et un projet CMake
est isolé dans une classe `Lang` (`RustLang`, `PythonLang`, `CLang`) :
arborescence, fichier à produire, commande de test, allowlist de la sandbox,
parsing du résultat.

| | Rust | Python | C |
|---|---|---|---|
| fichier produit | `src/lib.rs` | `solution.py` | `src/solution.c` |
| tests cachés déposés dans | `tests/hidden.rs` | `test_hidden.py` | `tests/hidden.c` |
| pré-vérification | — | `python3 -m py_compile` | `cmake -S . -B build` puis `cmake --build build --target hidden` |
| notation | `cargo test --test hidden` | `python3 -m unittest -v test_hidden` | `./build/hidden` |
| écritures autorisées | `src/*.rs`, `tests/*.rs` | `*.py` à la racine | `src/*.{c,h}`, `tests/*.{c,h}` |
| commandes autorisées | `cargo build/check/test/clippy/fmt` | `python3 -m unittest/pytest/py_compile`, `python3 <f>.py` | `cmake -S . -B build`, `cmake --build build`, `ctest`, `./build/<exe>` |

En Python, un `compile_error` correspond à une erreur de syntaxe ou d'import
détectée par `py_compile` avant même de lancer les tests. En C, c'est une erreur
de `cmake` ou du compilateur.

### La série C

Le `CMakeLists.txt` est **fourni** par le harnais et n'est pas modifiable : il
compile `src/*.c` en une bibliothèque statique `task` et produit un exécutable
par fichier `tests/*.c`. Le modèle ne peut donc pas ajouter de dépendance.

Compilation en **C11**, `-Wall -Wextra`, et surtout
`-fsanitize=address,undefined -fno-sanitize-recover=undefined` : un débordement,
une lecture non initialisée, un `free` invalide ou un dépassement d'entier signé
font échouer les tests au lieu de passer par hasard. Si le binaire est tué en
cours de route par un sanitizer, le harnais compte les tests déjà passés — c'est
un `fail` avec score partiel, pas un `compile_error`.

Le harnais dépose aussi `tests/harness.h`, un micro-runner d'assertions
(`TEST(nom) { … }`, `CHECK`, `CHECK_INT_EQ`, `CHECK_STR_EQ`, `CHECK_MEM_EQ`…)
que la suite cachée utilise et que le modèle peut réutiliser pour ses propres
tests. Sa sortie est calquée sur celle de `cargo test`, ce qui permet de la
noter avec le même parsing.

Les prototypes sont **redéclarés dans la suite de tests cachée**, jamais dans un
en-tête partagé : une signature approximative ne compile pas.

Options utiles :

| option | défaut | rôle |
|---|---|---|
| `--task-timeout` | `600` | budget en secondes par couple (tâche, mode) ; **au-delà on tue** |
| `--cargo-timeout` | `120` | budget par commande de compilation ou de test (cargo, unittest, cmake/ctest) |
| `--max-turns` | `12` | tours maximum en mode agentique |
| `--num-ctx` | `16384` | fenêtre de contexte Ollama (sans effet sur `litellm:`) |
| `--temperature` / `--seed` | `0.2` / `0` | reproductibilité |
| `--agent-protocol` | `auto` | `tools` (tool-calling natif), `text` (protocole textuel), `auto` bascule si le modèle ne supporte pas les outils |
| `--backend` | `ollama` | backend des modèles sans préfixe |
| `--litellm-base-url` | `$LITELLM_BASE_URL`, sinon `http://localhost:4000` | endpoint OpenAI-compatible |
| `--litellm-api-key` | `$LITELLM_API_KEY`, sinon `$OPENAI_API_KEY` | envoyée en `Authorization: Bearer` |
| `--litellm-extra-body` | — | JSON fusionné dans chaque requête, ex. `'{"num_ctx": 16384}'` |
| `--no-warmup` | — | saute l'appel de préchauffage (inutile et facturé sur une API distante) |

## Les deux modes

**`direct`** — un seul appel. Le modèle reçoit la spec et doit rendre
l'intégralité du fichier demandé (`src/lib.rs`, `solution.py` ou `src/solution.c`)
dans un seul bloc de code. C'est du **pass@1** : aucune boucle de correction,
aucun compilateur. Mesure la justesse « du premier coup ».

**`agentic`** — le modèle est lâché dans un vrai projet (cargo, module Python ou
projet CMake) avec quatre outils :

| outil | effet |
|---|---|
| `write_file(path, content)` | écrit dans les chemins autorisés du langage (le reste est refusé) |
| `read_file(path)` | relit un fichier du projet |
| `run_command(command)` | uniquement l'allowlist du langage (cargo en `--offline`, `python3 -m unittest`, `cmake`/`ctest`) |
| `finish(summary)` | déclare la tâche terminée |

Il boucle donc écrire → compiler → lire les erreurs → corriger, jusqu'à `finish`
ou épuisement des tours. Il peut écrire **ses propres** tests, ce qui n'influence
pas la note : la note vient toujours des tests cachés.

## Backend `litellm:`

Le client parle le dialecte **OpenAI en streaming** (`POST /v1/chat/completions`,
`stream: true`) : il marche avec un proxy LiteLLM, mais aussi avec n'importe quel
endpoint compatible. C'est le même harnais que pour Ollama — mêmes prompts,
mêmes quatre outils, même boucle agentique — seul le transport change ; **les
deux modes restent donc comparables** avec les lignes Ollama.

```bash
# le proxy en face, avec ta config de routage
litellm --config config.yaml            # écoute sur :4000

export LITELLM_API_KEY=sk-...           # ou --litellm-api-key
python3 bench.py --models litellm:gpt-4o-mini --no-warmup
```

Ce qui est repris du backend Ollama : streaming (couper la connexion arrête la
génération côté serveur, donc le budget `--task-timeout` est vraiment tenu),
tool-calling natif, bascule `auto` vers le protocole texte si le modèle refuse
les outils, tokens et coût quand le proxy les renvoie (usage de fin de flux,
en-tête `x-litellm-response-cost`).

Trois réserves :

- **`tok/s`** est mesuré du premier au dernier token, **réseau compris**, alors
  qu'Ollama expose son décodage pur (`eval_count / eval_duration`). Sur un
  endpoint distant, la latence du réseau est dans le dénominateur.
- **Les paramètres d'inférence appartiennent au serveur** derrière le proxy
  (quantisation, contexte, batching) : `--num-ctx` ne s'y applique pas. Utiliser
  `--litellm-extra-body '{"num_ctx": 16384}'` si le backend accepte le paramètre.
- **`--seed` n'est qu'une intention** : peu de fournisseurs le garantissent.

## Backend `claude:` — et ce qu'il ne prouve pas

Le CLI Claude Code s'authentifie avec ton **abonnement** (Pro/Max), pas avec une
clé API : aucun coût supplémentaire, mais ça consomme le quota du plan. Le
harnais lance :

```
claude -p --model <m> --system-prompt <mes prompts> --output-format json
        --safe-mode --no-session-persistence
        --tools ""                                   # mode direct
        --tools Read,Write,Edit,Bash                  # mode agentique
        --allowed-tools "Bash(cargo:*)"               # ou python3, ou cmake+ctest
        --permission-mode acceptEdits
```

`--safe-mode` neutralise CLAUDE.md, skills, plugins et hooks pour que la mesure
ne dépende pas de ta configuration locale. Le prompt passe par **stdin** : les
options `--tools` et `--allowed-tools` sont variadiques et avaleraient un prompt
placé en argument positionnel.

Trois réserves, reprises dans chaque rapport :

- **Le mode direct est comparable** : mêmes prompts exactement, tous les outils
  désactivés, un seul appel. C'est bien modèle contre modèle.
- **Le mode agentique ne l'est pas.** Claude Code apporte sa propre boucle, son
  propre format d'outils et sa propre gestion d'erreur. On compare deux *agents*,
  pas deux modèles.
- **`tok/s` n'a pas la même définition** selon le backend : décodage pur côté
  Ollama (`eval_count / eval_duration`), temps API bout en bout côté CLI, réseau
  compris. Les deux colonnes ne se lisent pas l'une en face de l'autre.

Le coût en dollars affiché pour les lignes `claude:*` est **notionnel** : sur un
abonnement il n'est pas facturé en plus, il sert juste d'ordre de grandeur.

## Les tâches

Des classiques dont le résultat attendu est connu et non ambigu, par difficulté
croissante. Les séries Rust, Python et C se recoupent volontairement (`rle`,
`word_freq`, `lru` sont posés dans les trois ; `asn1_ber` en Python et en C), ce
qui permet de comparer un modèle à lui-même d'un langage à l'autre.

**Rust** (`tasks/rust/`) — 55 tests

| tâche | contenu | tests | ce que ça teste |
|---|---|---|---|
| `rle` | run-length encoding + decoding | 12 | logique de base, `chars().peekable()`, compteurs multi-chiffres |
| `word_freq` | top-k des mots les plus fréquents | 10 | `HashMap`, départage lexicographique, minusculisation Unicode |
| `lru` | cache LRU (LeetCode 146) | 10 | conception d'une structure, `&mut self`, récence, ownership |
| `expr_eval` | analyseur descendant récursif | 23 | grammaire à 5 niveaux, associativité gauche **et** droite, `enum` d'erreurs |

**Python** (`tasks/python/`) — 95 tests

| tâche | contenu | tests | ce que ça teste |
|---|---|---|---|
| `rle` | idem Rust | 12 | idem |
| `word_freq` | idem, avec `str.isalnum()` | 11 | + renvoyer des `tuple`, pas des `list` |
| `lru` | idem, avec `__len__` | 11 | + ne pas confondre valeur `0` et absence |
| `expr_eval` | idem, sémantique `%` **de Python** (`-7 % 3 == 2`) | 25 | + hiérarchie d'exceptions, interdiction d'`eval()` |
| `asn1_ber` | décodeur de PDU ASN.1 en BER (X.690) | 36 | la plus dure du lot, voir ci-dessous |

**C** (`tasks/c/`) — 134 tests

| tâche | contenu | tests | ce que ça teste |
|---|---|---|---|
| `rle` | idem Rust, mais avec des `char *` alloués | 19 | propriété des chaînes, calcul de taille avant `malloc`, validation du décodage |
| `word_freq` | idem, avec un tableau de `WordCount` possédé | 15 | table de hachage à la main, `qsort` avec départage, `strdup`/`free` symétriques |
| `lru` | idem, type opaque + `lru_keys` pour observer la récence | 17 | hachage **et** liste doublement chaînée, `out_value` pour ne pas confondre valeur `0` et absence, O(1) exigé |
| `csv` | analyseur RFC 4180 | 25 | machine à états sur octets, guillemets échappés, `\r\n` vs `\r` isolé, deux familles d'erreurs |
| `dijkstra` | plus courts chemins + reconstruction | 19 | tas binaire (O((V+E) log V) exigé), départage déterministe des prédécesseurs, pas d'écriture partielle |
| `ber` | décodeur ASN.1 BER, arbre de TLV possédé | 39 | la plus dure du lot, voir ci-dessous |

### `expr_eval` — le premier palier

Les trois premières tâches saturent à 100 % dès qu'un modèle est correct. La
difficulté d'`expr_eval` tient aux détails les plus souvent ratés : `^`
associatif à droite (`2^3^2 == 512`, pas 64), l'unaire qui lie moins fort que la
puissance (`-2^2 == -4`, pas 4), et le bon variant d'erreur pour chaque entrée
invalide.

### `asn1_ber` — le second palier

Décodeur BER complet, en Python. Il faut sortir un arbre de TLV à partir
d'octets bruts, avec les formes que les décodeurs naïfs ratent :

- **tag en forme longue** (`0x1F` puis base-128 continué) — `9F 81 00` = tag 128 ;
- **longueur en forme longue** (`0x81`, `0x82`…) et **longueur indéfinie**
  (`0x80` terminée par `00 00`), la vraie spécificité de BER face à DER ;
- **règle du premier arc d'OID** : `40×X + Y`, mais `X = 2` et `Y = v - 80`
  dès que `v >= 80` — d'où `81 34` → `2.100` ;
- INTEGER en **complément à deux signé** ;
- six familles d'erreurs à distinguer (troncature, octets en trop, longueur
  indéfinie sur un primitif, `0xFF` réservé, indéfinie non close).

Les tests se terminent par le décodage d'une **vraie PDU SNMP GetRequest**
complète, jusqu'à l'OID `1.3.6.1.2.1` et au `request-id` `305419896`.

### `c/ber` — le troisième palier

Le même décodeur, en C, où la difficulté du format s'ajoute à celle du langage.
En plus de tout ce qui précède :

- l'arbre de `BerTlv` est **possédé** et doit se libérer d'un seul `ber_free`,
  y compris quand le décodage échoue à mi-parcours (les nœuds déjà construits ne
  doivent ni fuir ni être libérés deux fois) ;
- le champ `value` **pointe dans le tampon d'entrée**, sans copie : un test
  vérifie l'identité du pointeur ;
- l'accumulation d'un INTEGER passe par un type non signé, sinon le décalage
  d'une valeur négative est un comportement indéfini que le sanitizer attrape ;
- `BER_OVERFLOW` distingue ce qui ne tient pas dans un `unsigned long` (numéro
  de tag, sous-identifiant d'OID) ou dans un `long long` (INTEGER de plus de
  8 octets) de la simple troncature.

### Structure d'une tâche

```
tasks/<langage>/<nom>/
  spec.md                             # ce que voit le modèle
  tests.rs | tests.py | tests.c       # suite cachée, jamais montrée au modèle
  reference.rs | reference.py | reference.c   # solution de référence, sert au --self-test
```

Les pièges sont volontaires et documentés dans chaque spec.

## Notation

Pour chaque couple (tâche, mode), le harnais recopie les sources produites par le
modèle dans un **projet neuf**, y injecte la suite cachée (`tests/hidden.rs`,
`test_hidden.py` ou `tests/hidden.c`) et la lance. Statuts possibles :

| statut | signification |
|---|---|
| `pass` | tous les tests cachés passent |
| `fail` | ça compile, des tests échouent (score partiel = passés/total) |
| `compile_error` | ça ne compile pas → 0 |
| `no_code` | le modèle n'a rendu aucun code exploitable → 0 |
| `timeout` | budget dépassé, ou flux coupé côté serveur ; génération et processus tués |
| `error` | backend injoignable, modèle inconnu, refus de l'API, etc. |

## Mesures collectées

Par couple (modèle, tâche, mode) :

- **exactitude** : statut, tests passés / total, score
- **temps** : mur total, temps passé dans le LLM, temps passé dans cargo,
  time-to-first-token
- **tokens** : prompt, générés, tok/s — décodage pur côté Ollama
  (`eval_count / eval_duration`, donc hors chargement du modèle), fenêtre
  premier → dernier token réseau compris côté `litellm:`
- **comportement agentique** : tours, appels d'outils, écritures, commandes
  cargo, actions malformées, est-ce que ses propres tests passaient
- **code** : lignes non vides produites

Le modèle est préchargé (warm-up) avant la première tâche pour que le temps de
chargement des poids ne pollue pas les mesures. Sur un backend `litellm:` le
warm-up ne sert plus qu'à valider tôt l'endpoint et la clé — `--no-warmup` le
supprime si l'appel est facturé.

## Sorties

```
runs/<horodatage>/
  report.md        # tableaux détaillés + synthèse + extraits d'échec
  results.json     # toutes les métriques, exploitable
  <modèle>__<tâche>__<mode>/
    candidate.rs   # le code final du modèle (.rs, .py ou .c selon la tâche)
    raw_reply.md   # réponse brute (mode direct)
    transcript.json# déroulé des tours et des outils (mode agentique)
    agent/         # le projet dans lequel l'agent a travaillé
    grading/       # le projet de notation, avec les tests cachés
```

Le rapport est réécrit après **chaque** couple : interrompre le benchmark ne
fait rien perdre.

## Limites connues

- `pass@1` sur un seul échantillon par tâche : la variance modèle-à-modèle est
  réelle, augmente le nombre de tâches ou refais tourner avec d'autres `--seed`
  pour conclure sérieusement.
- Un timeout en cours de génération coupe la connexion HTTP, ce qui arrête
  Ollama côté serveur ; le modèle reste chargé (`keep_alive`). Derrière un proxy
  LiteLLM, l'arrêt effectif dépend du fournisseur : la requête peut être
  facturée entièrement même si on raccroche.
- Le timeout HTTP est un timeout **de lecture** (120 s max entre deux blocs) :
  un serveur muet plus longtemps que ça est signalé `timeout` avec la raison
  exacte, même si le budget global n'est pas épuisé.
- La sandbox est volontairement minimale (allowlist de chemins et de commandes
  par langage) : c'est une barrière contre les dérapages, pas contre un modèle
  hostile.
