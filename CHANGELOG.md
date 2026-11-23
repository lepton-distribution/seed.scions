# Journal des modifications

## 0.6.3.4

Correction ; formats de fichiers et commandes inchangés.

### Corrections

- **Un seed cloné hors de sa version arrête `seed-update` et `graft-update`.**
  Ils avançaient le dépôt d'un seed distant cloné par `seed-add --version V`
  (`depots/<nom>/V`) sur sa branche courante, sans le comparer à `V` : un seed
  remis à la main sur une autre branche était avancé, puis lu, et ses scions
  clonés et greffés sous cette autre branche. Un seed détaché était lu tel quel.
  Le seed doit désormais être à `V` (branche extraite, commit du tag) ; sinon la
  commande s'arrête (code 1) avant toute modification, nomme le seed et la
  commande de remise. Un seed cloné à un tag est vérifié, jamais avancé. Le seed
  est reconnu à sa place : dépôt `depots/<nom tiré de son URL origin>/V`.
- **Le message d'échec de git donne la cause après un avertissement.** Il
  gardait la première ligne non vide de git, qui peut être un avertissement
  (`warning: Could not find remote branch … to clone.` de `git clone
  --single-branch` avant git 2.50) ou une astuce (`hint:` de `git merge
  --ff-only`). Il garde la première ligne `fatal:` ou `error:`, en anglais ou en
  français (`fatal` ou `erreur`, une espace insécable, puis le deux-points), sinon,
  comme avant, la première ligne non vide ; toujours sur une seule ligne.
- Inchangés : seed donné par un chemin, seed sans `origin`, seed à sa version ;
  contrôles des clones ; codes de retour.

## 0.6.3.3

Correction ; formats de fichiers et commandes inchangés.

### Corrections

- **Un clone existant repris par `seed-clone` est contrôlé.** `seed-clone`
  réutilisait sans contrôle un clone déjà présent dans `depots/`, et `graft` le
  greffait ensuite sous la version déclarée, même s'il était sur une autre
  branche ou un autre commit (par exemple un clone laissé par un checkout en
  échec de scion ≤ 0.6.3.1). Un clone que `seed-clone` adopte -- scion ordinaire
  distant qui n'est pas encore greffé avec ce clone et cette version -- doit
  désormais être à sa version déclarée (branche extraite, commit du tag) ; sinon
  la commande s'arrête avant tout clonage (code 1), nomme les clones et la
  commande de remise (`git -C … switch …`), et ne change ni la liste greffée ni
  les clones. Un clone déjà greffé n'est pas contrôlé : le travail sur une autre
  branche se regreffe comme avant.
- **Le clone existant d'un seed distant est contrôlé par `seed-add`.** Il était
  avancé depuis l'amont de sa branche courante et lu tel quel, même hors de
  `--version`. Hors de la version demandée, la commande s'arrête (code 1), rien
  n'est modifié.
- **Le message d'échec de git donne la cause.** Il gardait la dernière ligne de
  git, souvent son conseil générique (« and the repository exists. »). Il garde
  la première ligne non vide, quelle que soit la langue de git, sur une seule
  ligne ; `-v` journalise toute la sortie. `git clone -b` est lancé avec
  `--quiet`, pour que sa ligne de progression ne vienne pas en tête.
- Inchangés : clone à sa version, clone manquant, graine donnée par un chemin ;
  `graft`, `graft --scion` ; `seed-add`, `seed-update` et `graft-update` (contrôles
  de 0.5.4.0) ; clé projetée (P-V1, P-E1) ; codes de retour. `seed-update` et
  `graft-update` ne comparent toujours pas un seed à une version.

## 0.6.3.2

Correction ; formats de fichiers et commandes inchangés.

### Corrections

- **Un clone est fait à sa version déclarée, ou pas du tout.** Sans
  `--single-branch`, un scion ordinaire et un seed distant étaient clonés, puis
  mis sur leur version par `git checkout`. Un checkout en échec (version absente
  de l'origine, origine vide, branche homonyme d'un répertoire du dépôt)
  laissait le clone sur la branche de l'origine, sans le dire ; `seed-clone`, et
  `seed-add` pour un seed distant, le réutilisaient ensuite sans contrôle, et il
  était greffé. Une version qui n'était qu'un chemin du dépôt (`git checkout
  scion`) réussissait en silence. git met désormais le clone sur sa version
  (`git clone -b`), toutes les branches reçues : une version qui n'est ni une
  branche ni un tag de l'origine est refusée avant tout arbre de travail, et
  aucun clone n'est gardé. Une branche homonyme d'un répertoire est clonée.
- Une version commit complet d'un scion ordinaire, hors de la règle (« un nom
  de branche ou de tag »), est refusée dès le clonage ; elle était acceptée,
  puis refusée au passage suivant par le contrôle de version de 0.5.4.0.
- Inchangés : branche (suivie de son amont) et tag (`HEAD` détaché) ;
  `--single-branch` ; clé projetée (P-V1, clone laissé en place). Un clone
  laissé hors de sa version par une version antérieure n'est pas touché.

## 0.6.3.1

Correction ; formats de fichiers et commandes inchangés.

### Corrections

- **Un clonage en échec ne laisse aucun répertoire dans `depots/`.** Avant de
  cloner, scion crée les parents de la destination ; git retire la destination
  d'un clonage en échec, jamais ses parents. En 0.6.3.0, un `seed-add` dont le
  clonage échouait laissait ainsi `depots/<shelf>/<prefix>` vide, et un miroir
  inaccessible toute la chaîne `depots/.mirrors/<hôte>/<chemin>`. Les
  répertoires que l'appel a créés pour le clone sont désormais retirés, du plus
  profond au plus haut, s'ils sont vides : scion ordinaire, seed distant
  (`seed-add`), clé projetée, dépôt de travail d'un miroir (`mirror-sync`,
  `--dry-run` compris). Un répertoire qui existait avant l'appel, vide ou non,
  est gardé. Un clone réussi reste en place comme avant : version introuvable
  (P-V1), checkout en échec, dépôt de travail dont l'amont est inaccessible
  (M-C6). `-v` nomme les répertoires retirés.

## 0.6.3.0

Évolution de la projection. Spécification : `doc/projection-miroir.md`, règle P-V7.
Formats inchangés ; git ≥ 2.35 est exigé dès qu'une clé projetée a un clone distant.

### Nouveautés

- **Extraction partielle des clones distants** (P-V7). Un clone de clé projetée
  n'extrait que les répertoires parents des fichiers sources de ses tables (union
  des clés qui partagent le clone), plus les fichiers placés directement à la
  racine et dans les répertoires ancêtres (`git sparse-checkout`, mode cône).
  Créé à la racine seule par `seed-add`, `seed-clone`, `seed-update` ou
  `graft-update`, il reçoit son ensemble à la greffe : élargi avant la pose des
  liens, réduit après la greffe réussie, si bien qu'une greffe en échec ne laisse
  aucun lien vers un fichier non extrait. Un message nomme chaque clone dont
  l'ensemble change ; `-v` liste les répertoires.
- Un clone extrait en entier par une version antérieure est converti par sa
  prochaine greffe ; les objets déjà reçus restent dans `.git`. Un emplacement
  local n'est jamais touché.
- git < 2.35 : erreur (code 1) avant tout clonage et toute greffe d'une clé
  projetée distante.

## 0.6.2.0

Correctif de la projection. Spécification : `doc/projection-miroir.md`, règle P-G6.

### Corrections

- **`graft --scion <porteur>` regreffe aussi ses clés projetées** (P-G6), et le
  dit par un message. C'est le pendant de P-P6 (`graft-remove <porteur>`). En 0.6.1.0, après
  `graft-remove`, `seed-clone` puis `graft --scion <porteur>`, les clés projetées
  étaient réinscrites dans la liste greffée sans aucun lien dans le trunk.
  `graft --scion <clé projetée>` ne change pas (P-G5).

## 0.6.1.0

Nouveau format facultatif `.scion.mirrors`, nouvelle commande `mirror-sync`. Un
rootstock sans `.scion.mirrors` se comporte exactement comme en 0.6.0.0.
Spécification : `doc/projection-miroir.md`, partie B.

### Nouveautés

- **Miroir de conservation.** `.scion.mirrors`, dans le `.scion/` d'une graine
  ou d'un porteur : lignes `<url du miroir> <url de l'amont>`. Ligne mal formée,
  URL locale, miroir associé à deux amonts : erreur (code 1) avec fichier et
  ligne.
- **`scion mirror-sync [rootstock] [--seed CHEMIN] [--dry-run] [URL…]`.** Dépôt
  de travail nu `depots/.mirrors/<hôte>/<chemin>` : références du miroir dans
  `refs/heads` et `refs/tags`, de l'amont dans `refs/amont/*`. Branches et tags
  seulement ; branche nouvelle ou en avance rapide et tag nouveau envoyés ; branche
  réécrite (ou miroir en avance), tag déplacé (même recréé sur le même commit),
  référence supprimée dans l'amont : signalés, jamais propagés. Un seul
  `git push --porcelain` par miroir, chaque référence nommée, jamais forcé ni
  destructif ; une référence refusée par le serveur est signalée. Miroir ou
  amont inaccessible : signalé, les autres miroirs traités. Codes : 0 sans
  signalement, 1 avec, 2 pour une URL non déclarée (vérifiée avant tout accès
  réseau) ou un échec git local.
- **Suggestion de la greffe.** Quand le clonage d'une URL déclarée comme miroir,
  ou la recherche de sa version, échoue, le message suggère `scion mirror-sync`.
  La greffe ne lit `.scion.mirrors` que pour cela.

## 0.6.0.0

Nouveau format facultatif `.scion.projections`, 6ᵉ colonne facultative de
`.scion.grafted.list`. Un rootstock sans projection se comporte exactement comme
en 0.5.4.0 : mêmes liens, mêmes messages, mêmes codes de retour, même liste
greffée. Spécification : `doc/projection-miroir.md`, partie A.

### Nouveautés

- **Projection d'un dépôt tiers.** Un dépôt sans répertoire `scion/` se greffe
  par des lignes `shelf nom motif destination` (inclusion) ou `shelf nom !motif`
  (exclusion) de `.scion.projections`. Les motifs portent sur la liste git du
  commit épinglé (`git ls-tree`), jamais sur le disque : un fichier non suivi
  n'est jamais projeté, un sous-module jamais, un lien committé l'est comme une
  feuille. Formes `d/**`, `d/*`, jokers dans le dernier segment, fichier. Une
  destination terminée par `/` remplace la base du motif ; sans `/`, elle
  renomme un fichier.
- **Erreurs explicites.** Ligne mal formée, motif ou exclusion sans
  correspondance, deux sources vers un même chemin, fichier contre répertoire,
  collision de casse dans le trunk (sur tout système) : code 1, toutes les
  erreurs d'une clé ensemble, chacune avec fichier et numéro de ligne.
- **Version épinglée.** Une clé projetée a pour version un tag ou un commit
  complet ; une branche, `*` et `?` sont refusés. Clone partiel
  (`--filter=blob:none --no-checkout`, puis `HEAD` détaché) sous
  `depots/<shelf>/<prefix>/<version>`. Un clone qui n'est pas à son commit, ou
  qui a des fichiers suivis modifiés, arrête la greffe avant le dégreffage. Un
  tag déplacé dans l'amont arrête `graft-update`, `seed-update` et `seed-add` ;
  un commit absent du clone est cherché par `git fetch origin`.
- **Scion porteur.** Un scion dont `scion/.scion/` contient un
  `.scion.projections` déclare les projections dont il dépend ; elles entrent
  dans la liste greffée avec, en 6ᵉ colonne, ce `.scion/`. Elles suivent le
  porteur quand `graft-update` l'avance, et sont retirées avec lui par
  `graft-remove`, ou quand il ne les déclare plus.
- `rootstock-information` affiche `scions projected: k` quand k > 0 ; `-v`
  détaille, par ligne de projection, le nombre de fichiers et les exclusions.

## 0.5.4.0

Changement de comportement de `graft-update`, `seed-update`, `seed-add` et
`graft`. Formats de fichiers et commandes inchangés.

### Nouveautés

- **Clones à leur version déclarée.** `graft-update`, `seed-update` et
  `seed-add` contrôlent chaque clone existant avant toute modification. Un
  clone avance par `git fetch`, puis `git merge --ff-only @{u}`, comme une
  graine. scion ne fait plus aucun `git pull`. Les cas suivants arrêtent la
  commande (code 1), trunk et clones inchangés :
  - clone sur une autre branche que sa version déclarée, ou en `HEAD`
    détaché ;
  - branche sans amont, ou divergée ;
  - clone en retard avec des modifications de fichiers suivis.

  Le message nomme tous les clones concernés et donne la commande de remise
  (`git -C <clone> switch <version>`). Un clone seulement en avance, ou à
  jour avec des modifications, est laissé tel quel. Auparavant, `git pull`
  tirait la branche courante, quelle qu'elle soit.
- **Versions déclarées par un tag.** Un tag est vérifié, jamais tiré : `HEAD`
  doit désigner son commit, et le tag ne doit pas avoir bougé dans l'amont
  (`origin`). Auparavant, `graft-update` échouait toujours sur un tel scion.
- **Trunk rétabli si la regreffe échoue.** `graft` et `graft-update` relèvent
  le trunk avant de le vider : liens, répertoires et `.scion.grafted.list`.
  Ils le remettent en place si la résolution des graines, le dégreffage ou la
  greffe échoue. Le message le signale, et compte les liens qui pointent vers
  des fichiers retirés des clones depuis. Auparavant, un conflit ou un échec
  de git après le dégreffage laissait un trunk vide.

## 0.5.3.0

Changement de comportement de `graft-update`, `seed-update` et de la greffe des
scions hors git ; formats de fichiers et commandes inchangés.

### Nouveautés

- **La graine avance avec son amont.** `graft-update` et `seed-update` avancent
  le dépôt git de chaque seed avant de lire ses scions : `git fetch`, puis
  `git merge --ff-only @{u}`. Un scion ajouté au seed publié est donc cloné et
  greffé sans `git pull` préalable. Les contrôles précèdent le dégreffage : un
  seed avec des modifications de fichiers suivis, ou dont la branche a divergé
  de son amont, arrête la commande (code 1) sans rien modifier, trunk compris.
  Les fichiers non suivis du seed n'arrêtent rien. Un seed hors git, sans amont,
  dans le dépôt qui contient le rootstock, ou seulement en avance sur son amont
  est laissé tel quel (`-v` le signale).
- **Scions hors git filtrés par les règles de git.** Un scion hors git suit les
  règles du filtre de 0.5.2.0 : ses propres fichiers `.gitignore` et
  `core.excludesFile` (par exemple `.DS_Store`), lus par `git ls-files` au
  travers d'un dépôt vide créé dans un répertoire temporaire ; rien n'est écrit
  dans la source. Un lien déjà greffé vers un chemin désormais exclu disparaît
  à la regreffe suivante. Un scion dont le dépôt contient le rootstock reste
  sans filtre.

## 0.5.2.0

Changement de comportement de la greffe et nouveau fichier de rootstock
facultatif ; formats existants et commandes inchangés.

### Nouveautés

- **Fichiers ignorés par git non greffés.** Pour chaque scion d'un dépôt git,
  les chemins non suivis que git ignore (`.gitignore`, `.git/info/exclude`,
  `core.excludesFile`) sont exclus de la greffe, répertoires ignorés compris
  (un appel `git ls-files --others --ignored --exclude-standard --directory`
  par scion). Deux clones qui portent le même fichier ignoré au même chemin ne
  sont plus en conflit. Un fichier suivi est toujours greffé, même s'il
  correspond à une règle ; un fichier non suivi non ignoré aussi. Un scion hors
  git, ou dont le dépôt contient le rootstock, n'est pas filtré. `-v` liste les
  chemins exclus ; leur nombre est affiché s'il est non nul.
- **`<rootstock>/.scion.trunk.tolerated`** : motifs `fnmatch` (nom du fichier,
  un par ligne, `#` en commentaire) des fichiers réguliers tolérés dans le
  trunk. Un fichier toléré ne bloque plus `ungraft`, `graft`, `graft --scion`,
  `graft-remove`, `graft-clean` ni `graft-update`, sans `--force` ; `ungraft`
  le supprime, `graft --scion` et `graft-remove` le suppriment avec le
  répertoire qu'ils retirent. Écrit sans motif par `rootstock-install` (pas par
  `--bare`) ; absent, rien n'est toléré.

### Changement

- Le message de refus d'un fichier régulier du trunk cite le fichier des motifs
  tolérés.

## 0.5.1.1

Correction ; formats de fichiers et commandes inchangés.

### Corrections

- Un scion distant de version `master` est cloné puis extrait sur `master`.
  Auparavant, sans `--single-branch`, le clone restait sur la branche pointée
  par le `HEAD` de l'origine, qui peut être une autre branche (`main`, branche
  de travail). Une version déclarée absente de l'origine fait désormais échouer
  la commande (code 2) au lieu de donner un clone sur une autre branche.

## 0.5.1.0

Ajouts compatibles et corrections ; formats de fichiers et commandes
existantes inchangés.

### Nouveautés

- **`seed-scion-add [--seed S] [--replace] shelf@nom version emplacement
  [chemin]`** déclare un scion dans un seed : une ligne dans
  `.scion.sources.list`, une dans `.scion.ramifications`. Un scion déjà déclaré
  est refusé, sauf `--replace`, qui remplace toutes ses lignes. Ni clone ni
  greffe : suivent `seed-clone` puis `graft --scion`.
- **`seed-scion-remove [--seed S] shelf@nom`** retire les lignes du scion des
  deux fichiers du seed. Commentaires et autres entrées sont conservés tels
  quels par les deux commandes.
- **`graft --scion shelf@nom`** (répétable) regreffe un seul scion : ses liens,
  reconnus par leur cible, sont retirés puis recréés depuis son contenu
  actuel ; le reste du trunk n'est pas touché. Un conflit annule l'appel et
  rétablit les anciens liens.
- **`graft-remove [--purge] [--force] shelf@nom`** retire un scion de la liste
  greffée et ses seules feuilles du trunk ; les répertoires vidés disparaissent,
  sauf ceux qu'un autre scion déclare. `--purge` supprime aussi le clone s'il a
  été fait par scion, qu'aucun autre scion ne l'utilise, qu'il est propre et
  qu'il n'a aucun commit absent de l'amont ; sinon refus, sans rien modifier.
- **`rootstock-install --bare`** ne crée que la signature, `depots/` et le
  trunk, sans `depots/origin` ni `depots/generation`.

### Corrections

- Un répertoire de scion qui rencontre un fichier ou un lien du même nom dans
  le trunk est un conflit signalé, annulé, code 1. Auparavant : trace Python
  sans annulation (fichier puis répertoire), ou greffe écrite **dans le clone**
  d'un autre scion à travers un lien versionné vers un répertoire, avec le
  code 0.
- Le message de conflit nomme le scion propriétaire d'un répertoire au lieu de
  « trunk ».
- `scion git` affiche la sortie de git (stdout, et stderr complet en échec) ;
  elle était capturée puis perdue.

## 0.5.0.1

Réécriture complète. L'outil devient un gestionnaire d'arbre de sources
générique : plus aucune chaîne ni aucun chemin propres à un projet dans le
paquet `scion/`, tout ce qui est spécifique vit dans les seeds.

### Ruptures

- **Greffe par feuilles.** Les répertoires du trunk sont de vrais répertoires,
  seuls les fichiers sont des liens symboliques, et ces liens sont *relatifs*.
  Auparavant des répertoires entiers étaient liés : quand deux scions
  partageaient une racine, le second était greffé à l'intérieur du working tree
  du clone du premier, et `ungraft` supprimait ensuite des liens dans les
  dépôts. Les clones restent désormais intacts, le résultat ne dépend plus de
  l'ordre des entrées, et un rootstock déplacé reste valide sans regreffe.
- **`SCION_ROOTSTOCK` supprimée.** L'outil ne lit ni n'écrit aucune variable
  d'environnement. Le rootstock est le répertoire portant
  `.scion.rootstock.signature`, trouvé en remontant depuis le répertoire
  courant. Dans un `.scion.sources.list`, un chemin local relatif est relatif au
  rootstock et un `$` dans un chemin local est une erreur, accompagnée du chemin
  de remplacement attendu. Les seeds existants doivent être corrigés (voir la
  section « Migration » du README).
- **`~/.scion.settings/` supprimé.** Ces fichiers étaient écrits mais jamais
  relus. Le nom du trunk est celui du répertoire portant `.scion.grafted.list`,
  ou celui donné par `--trunk`.
- **Windows n'est plus supporté** ; le contournement `CreateSymbolicLinkW`
  disparaît. Linux et macOS.
- **Commandes retirées** : `seed-list` et `seed-tag` (cette dernière n'avait
  jamais été implémentée). Les `graft-add`, `graft-remove`, `graft-replace` et
  `graft-refresh` annoncées dans l'en-tête de l'ancien script n'existent pas.
- **Chemins relatifs dans `.scion.grafted.list`.** Les chemins situés dans le
  rootstock y sont écrits relativement à lui, au lieu d'être absolus.
- **`rootstock-install`** ne crée plus que le layout générique
  (`depots/generation/building/scion/building/{projects,staging/lib,output}` et
  `depots/origin/scion/sources`). La branche « layout Lepton » était de toute
  façon inatteignable, `--trunk` valant `trunk` par défaut.
- **`graft-clean`** vide la liste greffée au lieu de supprimer le fichier :
  c'est lui qui marque le trunk.
- **`ungraft`** refuse de vider un trunk contenant un fichier régulier qui n'est
  pas une greffe, sauf avec `--force`, qui le conserve et dégreffe le reste.

### Corrections

- Un conflit de greffe (deux scions fournissant le même fichier) est signalé
  avec ses deux origines et fait échouer la commande sans laisser de trunk
  partiel. L'ancien outil gardait silencieusement le premier arrivé.
- La version `?` fonctionne à nouveau pour des versions numériques : la
  sélection n'amorce plus sa comparaison sur la chaîne vide, ce qui la faisait
  échouer silencieusement. Le comparateur lui-même est inchangé.
- Un scion sans suffixe `::` (par exemple `building`) ne provoque plus
  d'`IndexError`.
- Chaque dépôt n'est cloné et mis à jour qu'une fois, même quand plusieurs
  scions en proviennent : le seed `master` de Lepton passe de 16 `git pull` sur
  le même clone à un seul.
- Un lien symbolique versionné dans un dépôt est greffé comme lien, jamais suivi.
- L'absence de `<chemin dans le dépôt>/scion/` est signalée après le clone, et
  non plus au moment de la greffe.
- Les variables globales mutables du module, jamais réinitialisées, ont disparu,
  ainsi que la variable locale masquant `rootstock_trunk_dir` et le
  `location_grafted` résiduel de `graft_update`.

### Divers

- Codes de retour : `0` succès, `1` erreur utilisateur, `2` échec git. Plus
  aucune erreur ne se termine par `exit(0)`.
- `subprocess.run` avec une liste d'arguments partout ; plus de `os.system` ni
  de `shell=True`. `scion git --args` est découpé par `shlex.split`.
- `logging` à la place des `print` de debug ; `print` n'existe plus que dans
  `cli.py`.
- `setup.py` remplacé par `pyproject.toml` ; `requirements.txt` et `MANIFEST.in`
  supprimés. `requires-python = ">=3.10"`.
- La version est lue dans `scion/__init__.py`, seule source de vérité.
- Suite de tests (`tests/`) exécutable sans réseau, avec un test d'intégration
  optionnel sur l'arbre Lepton réel activé par `SCION_TEST_NETWORK`.
