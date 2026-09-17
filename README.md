# bench — évaluation d'un LLM sur du code Rust, Python et C

Harnais d'évaluation qui fait écrire du code à un modèle (local via Ollama,
n'importe quel fournisseur via LiteLLM, ou Claude via le CLI) et note le résultat
avec une **suite de tests cachée** que le modèle ne voit jamais. Trois langages,
deux modes, 18 tâches, 330 tests.

## Installation

Rien à installer côté harnais : Python 3 (bibliothèque standard uniquement),
`cargo` pour la série Rust, `cmake` et un compilateur C (clang ou gcc) pour la
série C. Puis, selon le backend visé, un Ollama qui tourne, un proxy LiteLLM
joignable, ou le CLI `claude`.

## Utilisation

```bash
# 1. vérifier que les tests cachés sont justes (les solutions de référence doivent passer 100 %)
python3 bench.py --self-test

# 2. évaluer un modèle sur tout le benchmark (21 tâches × 2 modes)
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
| `--max-turns` | `30` | tours maximum en mode agentique |
| `--num-ctx` | `32768` | fenêtre de contexte Ollama (sans effet sur `litellm:`) |
| `--temperature` / `--seed` | `0.2` / `0` | reproductibilité |
| `--seeds` | `0` | graines séparées par des virgules : un tirage par graine, pour un pass@1 moyenné |
| `--agent-profile` | `cc` | harnais imité : `cc` (Claude Code) ou `kilo` (kilocode/Roo) |
| `--agent-protocol` | `auto` | `tools` (tool-calling natif), `text` (protocole textuel), `auto` bascule si le modèle ne supporte pas les outils — y compris quand le serveur échoue à relire l'appel |
| `--machine` | sondée | description de la machine d'inférence, ex. `"RTX 6000 Blackwell 96 Go"` |
| `--no-show` | — | ne pas relever la fiche `ollama show` des modèles |
| `--backend` | `ollama` | backend des modèles sans préfixe |
| `--litellm-base-url` | `$LITELLM_BASE_URL`, sinon `http://localhost:4000` | endpoint OpenAI-compatible |
| `--litellm-api-key` | `$LITELLM_API_KEY`, sinon `$OPENAI_API_KEY` | envoyée en `Authorization: Bearer` |
| `--litellm-extra-body` | — | JSON fusionné dans chaque requête, ex. `'{"num_ctx": 16384}'` |
| `--no-warmup` | — | saute l'appel de préchauffage (inutile et facturé sur une API distante) |
| `-v` / `--verbose` | — | trace les prompts envoyés, les réponses, les outils déclarés, ceux que le modèle demande et leur résultat ; `-vv` ajoute le contexte complet de chaque tour, les raisonnements, et ne tronque plus rien |

## Les deux modes

**`direct`** — un seul appel. Le modèle reçoit la spec et doit rendre
l'intégralité du fichier demandé (`src/lib.rs`, `solution.py` ou `src/solution.c`)
dans un seul bloc de code. C'est du **pass@1** : aucune boucle de correction,
aucun compilateur. Mesure la justesse « du premier coup ».

**`agentic`** — le modèle est lâché dans un vrai projet (cargo, module Python ou
projet CMake) avec six outils :

| outil | effet |
|---|---|
| `write_file(path, content)` | écrit dans les chemins autorisés du langage (le reste est refusé) |
| `edit_file(path, old, new)` | remplace un extrait **exact et unique** : la retouche chirurgicale, sans réécrire le fichier |
| `read_file(path)` | relit un fichier du projet |
| `list_files()` | inventorie le projet, fichiers fournis compris |
| `run_command(command)` | l'allowlist du langage, chaînable avec `&&` (cargo en `--offline`, `python3 -m unittest`, `cmake`/`ctest`) |
| `finish(summary)` | déclare la tâche terminée |

Il boucle donc écrire → compiler → lire les erreurs → corriger, jusqu'à `finish`
ou épuisement des tours. Il peut écrire **ses propres** tests, ce qui n'influence
pas la note : la note vient toujours des tests cachés.

### Deux profils de harnais

Le protocole compte autant que le modèle. `--agent-profile` choisit lequel on
imite :

| | `cc` (défaut) | `kilo` |
|---|---|---|
| imite | Claude Code | kilocode / Roo |
| transport | appels d'outils natifs | balises XML dans le texte |
| appels par tour | jusqu'à 4 | 1, le protocole l'impose |
| édition | `edit_file` | `apply_diff` (blocs `SEARCH`/`REPLACE`) |
| fin | `finish` | `attempt_completion` |

Le même modèle sous les deux profils dit ce que coûte le **harnais** — un écart
que mesurer un seul des deux profils cache entièrement. Les deux ne se comparent
pas ligne à ligne : `recap.py` leur donne des sections séparées.

Un modèle dont le serveur ne sait pas produire d'appels d'outils lisibles (Ollama
rend alors une 5xx `XML syntax error…`) **bascule automatiquement** sur le
protocole texte plutôt que de perdre la mesure.

### Tours, contexte, chaînage

Trois réglages qui décidaient du résultat plus que les modèles :

- `--max-turns` vaut **30** (et non 12) : à 12, les trois quarts des échecs
  mesurés étaient des boucles coupées, pas du code faux. Un run qui épuise ses
  tours est rapporté `turns` (« KO tours »), distinct de `fail`.
- `--num-ctx` vaut **32768** : en dessous, une boucle agentique longue dépasse la
  fenêtre et le serveur tronque en silence — le modèle perd la spec en route et
  on note ça comme une erreur de raisonnement. `prompt_peak` est consigné pour
  rendre la saturation visible.
- `run_command` accepte `a && b` : sans chaînage, configurer, compiler puis
  tester coûtait **trois tours en C** contre un seul en Rust (`cargo test`), et
  le projet CMake est désormais configuré d'avance. On mesurait le build, pas le
  modèle.

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

Avec `-v`, le harnais demande au CLI `--output-format stream-json --verbose` au
lieu de `json` : le flux JSONL laisse voir les outils demandés tour par tour, et
sa dernière ligne reste l'objet `type: result` d'où viennent les métriques —
elles ne changent pas.

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

Des classiques dont le résultat attendu est connu et non ambigu. Les séries
Rust, Python et C se recoupent volontairement (`rle`, `word_freq`, `lru` sont
posés dans les trois ; le décodeur BER en Python et en C), ce qui permet de
comparer un modèle à lui-même d'un langage à l'autre.

Les 18 tâches, dans l'ordre où `--self-test` les liste. « à produire » est le
point d'entrée attendu : la suite cachée n'appelle que ça, et une signature
approximative ne compile pas.

| tâche | à produire | tests | en une phrase | ce que ça teste vraiment |
|---|---|---|---|---|
| `c/ber` | `ber_decode` → arbre de `BerTlv` possédé, `ber_free` | 39 | décodeur ASN.1 BER (X.690) en C | la plus dure du lot : formes longues et indéfinies, `ber_free` unique même après échec à mi-parcours, `value` qui pointe dans l'entrée sans copie, débordements distingués de la troncature |
| `c/csv` | `CsvError csv_parse(const char *, CsvTable **)` | 25 | analyseur CSV RFC 4180 | machine à états sur octets, guillemets échappés, `\r\n` contre `\r` isolé, deux familles d'erreurs |
| `c/dijkstra` | `graph_new`/`graph_add_edge`, `dijkstra`, `dijkstra_path` | 19 | plus courts chemins avec reconstruction du chemin | tas binaire (O((V+E)·log V) exigé), départage déterministe des prédécesseurs, pas d'écriture partielle du résultat |
| `c/lru` | type opaque `LruCache` + `lru_keys` | 17 | cache LRU en C | hachage **et** liste doublement chaînée, `out_value` pour ne pas confondre la valeur `0` et l'absence, O(1) exigé |
| `c/rle` | `char *rle_encode(const char *)` / `rle_decode` | 19 | run-length encoding en C | propriété des chaînes, taille calculée avant `malloc`, validation du décodage |
| `c/word_freq` | `word_freq` → tableau de `WordCount` possédé | 15 | top-k des mots les plus fréquents en C | table de hachage à la main, `qsort` avec départage, `strdup`/`free` symétriques |
| `python/asn1_ber` | `decode(data: bytes) -> TLV` | 36 | le même décodeur BER, en Python | tag et longueur en forme longue, longueur indéfinie, règle du premier arc d'OID, INTEGER signé, six familles d'erreurs — finit sur une vraie PDU SNMP |
| `python/expr_eval` | `eval_expr(expr: str) -> float` | 25 | évaluateur d'expressions arithmétiques | grammaire à 5 niveaux, `^` associatif à droite, unaire moins liant que la puissance, `%` à la sémantique Python, `eval()` interdit |
| `python/json_report` | `report(path: str) -> dict` | 20 | agrégats sur un export JSON sale | **analyse de fichier** : montants et dates multi-formats, doublons, champs absents — tout se découvre en lisant `data/commandes.json` |
| `python/log_triage` | `triage(path: str) -> list` | 15 | regroupement des erreurs d'un journal | **analyse de fichier** : quatre écritures d'horodatage, traces multi-lignes à rattacher, journal non trié |
| `python/lru` | classe `LRUCache` avec `__len__` | 11 | cache LRU en Python | récence, capacité, ne pas confondre la valeur `0` et l'absence |
| `python/reverse_spec` | `rendu(path: str) -> str` | 11 | reproduire un rapport dont la spec est perdue | **analyse de fichier** : aucune règle donnée, tout se déduit en comparant l'entrée à la sortie attendue |
| `python/rle` | `encode(text: str)` / `decode(text: str)` | 12 | run-length encoding en Python | logique de base, compteurs multi-chiffres, décodage strict |
| `python/word_freq` | `top_k(text, k) -> list[tuple[str, int]]` | 11 | top-k des mots les plus fréquents | départage lexicographique, minusculisation Unicode, renvoyer des `tuple` et non des `list` |
| `rust/expr_eval` | `eval(expr: &str) -> Result<f64, EvalError>` | 23 | le même évaluateur, en Rust | même grammaire, plus un `enum` d'erreurs à faire correspondre exactement |
| `rust/lru` | `LruCache::new/get/put/len/is_empty` | 10 | cache LRU en Rust | conception d'une structure, `&mut self`, récence, ownership |
| `rust/rle` | `encode(&str) -> String` / `decode(&str) -> String` | 12 | run-length encoding en Rust | `chars().peekable()`, compteurs multi-chiffres |
| `rust/word_freq` | `top_k(&str, usize) -> Vec<(String, usize)>` | 10 | top-k des mots les plus fréquents en Rust | `HashMap`, départage lexicographique, minusculisation Unicode |

Par série : **Rust** 55 tests, **Python** 141, **C** 134.

### `expr_eval` — le premier palier

`rle`, `word_freq` et `lru` saturent à 100 % dès qu'un modèle est correct. La
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

### `json_report`, `log_triage`, `reverse_spec` — l'analyse de données

Ces trois tâches Python ne mesurent pas la même chose que les autres : le code à
écrire y est court et sans finesse algorithmique, mais **il est impossible de
l'écrire correctement sans avoir lu le jeu de données livré avec la tâche**. La
spec dit qu'un problème existe, le fichier dit sous quelle forme.

| tâche | entrée | ce qu'il faut trouver dans le fichier |
|---|---|---|
| `json_report` | `data/commandes.json` | montants tantôt nombres tantôt texte (virgule décimale, séparateur de milliers dont un **insécable**), euro écrit `EUR`/`eur`/`€`/absent, trois formats de date dont un datetime, une date bien formée mais inexistante (`2026-02-30`), doublons d'`id`, champs absents ou `null` |
| `log_triage` | `data/app.log` | quatre écritures d'horodatage dont un **epoch**, niveaux en casse libre et entre crochets, traces d'exception multi-lignes à rattacher à leur en-tête, journal **non trié** (l'ordre des lignes n'est pas l'ordre du temps) |
| `reverse_spec` | `data/ventes.json` + `data/rapport_attendu.txt` | **aucune règle n'est donnée** : filtre, normalisation, tri, départage et formatage se déduisent en comparant l'entrée à la sortie attendue |

Les suites cachées appellent la fonction sur **d'autres** fichiers que celui
livré : coder en dur le résultat du fichier fourni ne rapporte qu'un test.
`reverse_spec` est le discriminant le plus dur du lot — un modèle qui survole
produit un rapport plausible et rate tout le reste.

### Structure d'une tâche

```
tasks/<langage>/<nom>/
  spec.md                             # ce que voit le modèle
  tests.rs | tests.py | tests.c       # suite cachée, jamais montrée au modèle
  reference.rs | reference.py | reference.c   # solution de référence, sert au --self-test
  data/                               # facultatif : jeux de données à analyser
  depart/                             # facultatif : fichiers posés dans le projet avant l'agent
  corrige/                            # facultatif : modules compagnons de la référence
  task.json                           # facultatif : {"type": …, "proteges": [...]}
```

`depart/` est ce qui distingue une tâche de réparation d'une tâche vierge : son
contenu est recopié dans le projet (chemins relatifs conservés) avant que l'agent
n'arrive — du code à réparer, des modules qui existent déjà, un test visible.
`proteges` liste les fichiers que l'agent n'a **pas** le droit de modifier : une
tentative est refusée et comptée (`denials`), ce qui en fait une mesure de
comportement et pas seulement un garde-fou. `corrige/` contient les versions
complètes des modules compagnons, pour que `--self-test` ait quelque chose à
importer.

Les pièges sont volontaires et documentés dans chaque spec.

### Trois tâches qui ne sont pas du greenfield

Les autres tâches partent d'un fichier vide, ce qui n'est pas le quotidien d'un
agent. Ces trois-là partent de code existant :

- **`c/ring_repair` (réparation)** — un tampon circulaire livré avec trois
  défauts (écriture hors bornes à l'enroulement, tête qui ne repasse pas au
  début, longueur inversée). Le test `tests/visible.c` est fourni **et
  protégé** : il faut réparer le code, pas le contrat. Le code livré passe 7
  tests cachés sur 15.
- **`python/etl_multi` (multi-fichiers)** — `normalise.py` est fourni complet,
  `agrege.py` est fourni **vide** (`NotImplementedError`), et `solution.py` doit
  orchestrer les deux. Les tests cachés visent `agrege` directement : recopier sa
  logique dans `solution.py` au lieu de l'implémenter là où elle vit ne passe pas.
  Il faut lire le code fourni, l'énoncé ne répète pas ses signatures.
- **`python/api_contract` (intégrité)** — trois règles délibérément
  contre-intuitives (arrondi des milieux **à l'écart de zéro**, contrairement à
  `round()` ; `None` dans un patch qui veut dire « ne touche pas » ; clé de tri
  qui garde le nom d'origine). Le test `test_contrat.py` est fourni et protégé :
  il a raison même quand il a l'air d'avoir tort. La tentation de corriger le
  test plutôt que le code est exactement ce qu'on mesure.

Si `data/` existe, son contenu est recopié tel quel à la racine du projet
(`data/…`), pour le grading comme pour les deux modes :

- en **mode agentique**, l'agent le trouve sur son disque et peut l'inspecter
  (`read_file`, `Read`, ou un `python3 script.py` d'exploration) ;
- en **mode direct**, le modèle n'a pas de système de fichiers : les fichiers de
  données sont **inlinés dans le prompt** (tronqués à 20 000 caractères), sinon
  la tâche serait ingagnable. La comparaison direct/agentique reste donc
  honnête, au coût d'un prompt plus gros.

## Répéter les mesures

Sur 18 tâches et un seul tirage, un écart d'une ou deux tâches entre deux modèles
est du bruit. `--seeds 0,1,2` mesure chaque couple une fois par graine :

```bash
python3 bench.py --models qwen3.8:latest --seeds 0,1,2
```

`recap.py` agrège alors les tirages : la cellule donne la part de tirages réussis
(`2/3`) et les moyennes, le classement donne un **pass@1 moyen** (`14.3/18`) et
une colonne **étendue** — le nombre de tâches réussies par la plus mauvaise et la
meilleure graine. C'est l'écart en deçà duquel un point de classement ne veut
rien dire.

## Notation

Pour chaque couple (tâche, mode), le harnais recopie les sources produites par le
modèle dans un **projet neuf**, y injecte la suite cachée (`tests/hidden.rs`,
`test_hidden.py` ou `tests/hidden.c`) et la lance. Statuts possibles :

| statut | signification |
|---|---|
| `pass` | tous les tests cachés passent |
| `fail` | ça compile, des tests échouent (score partiel = passés/total) |
| `turns` | la boucle agentique a épuisé ses tours sans conclure : le modèle n'avait pas fini, pas forcément faux |
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
- **comportement agentique** : tours, appels d'outils, écritures, **éditions
  (et éditions ratées)**, commandes, actions malformées, **refus** (chemin
  interdit ou fichier protégé), **pic de contexte**, est-ce que ses propres tests
  passaient, et si la boucle s'est arrêtée faute de tours
- **code** : lignes non vides produites

Chaque mesure porte aussi sa **graine** et son **profil de harnais**, qui font
partie de son identité : deux tirages ne s'écrasent pas, et `cc` ne se compare
pas à `kilo`.

Et, une fois par run, la **fiche de chaque modèle Ollama**, relevée par
`ollama show` (`/api/show`) : architecture, nombre de paramètres, quantisation,
format, contexte natif, taille sur disque, empreinte, capacités et réglages du
modelfile que le benchmark ne fixe pas lui-même (`top_k`, `top_p`, `min_p`…).
`--machine` décrit la machine d'inférence : sur un serveur distant, aucune sonde
locale ne peut voir le GPU d'en face, et le harnais ne prétend plus décrire le
poste qui pilote (il le note à part, sous `machine_pilote`).

Sans elle, deux runs de `gemma4:31b` peuvent porter le même nom et des poids
différents — un tag repoussé, une quantisation refaite — et la comparaison ne
veut plus rien dire : le nom d'un tag n'identifie rien, l'empreinte si.
`--no-show` s'en passe. Les runs d'avant cette fiche se rattrapent après coup
avec `recap.py --sonder`, qui interroge le serveur et garde les réponses dans
`runs/_modeles.json`.

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
fait rien perdre. `report.md` s'ouvre sur la fiche des modèles mesurés, et
`results.json` la garde sous `config.model_details`.

### Récapitulatif de tous les runs

`recap.py` balaie `runs/`, ne garde que la mesure **la plus récente** pour chaque
`(machine, hôte, backend, modèle, tâche, mode)` et engendre un document
**Typst**, compilé en PDF si `typst` est installé.

```bash
python3 recap.py                                  # runs/recapitulatif.typ + .pdf
python3 recap.py --backend ollama --mode direct   # filtres
python3 recap.py --modeles-par-tableau 4          # colonnes par tableau de détail
python3 recap.py --no-pdf --print                 # source Typst sur stdout
```

Un seul mode est rapporté, **`agentic` par défaut** : c'est celui qui exerce la
boucle d'outils, et mêler les deux doublait la hauteur du tableau pour des
mesures qui ne se comparent pas. `--mode direct` rapporte l'autre.

Chaque contexte de mesure donne deux vues. Le **classement** met un modèle par
ligne — tâches réussies, tests passés, temps, tours, tokens, et un profil en
barre empilée des statuts. Le **détail** met une tâche par ligne et un modèle
par colonne, par paquets de six modèles (`--modeles-par-tableau`) dans l'ordre
du classement : plutôt que d'écraser vingt colonnes sur une page, le tableau
s'étend sur plusieurs, l'en-tête se répétant en haut de chacune.

Le classement porte les paramètres et la quantisation de chaque modèle, et une
section **Modèles mesurés** détaille les poids derrière les noms (contexte
natif, taille, empreinte, capacités, réglages du modelfile) — pour les runs qui
en portent la fiche, ou après un `recap.py --sonder`.

Une cellule vaut `statut · tests passés/total`, puis `temps · tours` en gris ;
le statut est coloré, teinte le fond de la cellule et dit *pourquoi* c'est KO :
`KO tests`, `KO compil`, `KO délai`, `KO backend`, `KO vide`. Une section par
contexte de mesure — mélanger deux machines ou deux backends dans un même
tableau ferait comparer ce qui n'est pas comparable.

`compare.py` reste utile pour l'autre question : confronter deux runs précis, en
markdown.

### Mettre un modèle de côté

Un modèle essayé puis abandonné, ou mesuré deux fois sous deux tags (un tag nu
et son `:latest`, par exemple) encombre le récapitulatif sans rien lui
apprendre. `archive.py` le met de côté sans rien perdre :

```bash
python3 archive.py --models muse-glimmer:latest,qwen3.8:27b -n   # simulation
python3 archive.py --models muse-glimmer:latest,qwen3.8:27b      # archivage
python3 archive.py --liste                                       # l'inventaire
python3 archive.py --restaurer --models qwen3.8:27b              # marche arrière
```

Les mesures et leurs dossiers de travail partent dans `runs/_archive/<run>/` ;
`bench.py`, `compare.py` et `recap.py` ignorent les dossiers commençant par `_`.
Un run dont plus rien ne reste part en entier, `report.md` compris ; un run
seulement écorné garde son `report.md` d'origine, qui décrit alors des mesures
sorties de son `results.json`.

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
