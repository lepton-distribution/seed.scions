# Étape SCION — Réécriture courte de l'outil `scion`

<!-- Provenance : généré depuis l'analyse de scion.py v0.4.1.3-develop via la méthodologie
     lepton-portage-instructions (archétype Infrastructure / outillage). Premier jet à relire
     par le commanditaire. Toutes les décisions de cadrage ont été tranchées (tableau
     « Décisions actées ») ; toute question nouvelle est un point d'arrêt, pas une déduction. -->

## Contexte

`scion` (dépôt `lepton-distribution/seed.scions`, fichier `scion/scion.py`, 1416 lignes, Python 3)
est le gestionnaire de l'arbre des sources Lepton. Il compose un arbre unique (le *trunk* d'un
*rootstock*) par superposition de sous-arbres (*scions*) issus de plusieurs dépôts git, décrits par un
manifeste (*seed*) : `scion/.scion/.scion.ramifications` et `scion/.scion/.scion.sources.list`.
Le seed de référence pour ce chantier est `lepton-distribution/lepton-seed.scions`, **branche
`original-tree`** (dernier commit nov. 2020). Il déclare deux scions : `lepton original::tree master`
→ `lepton-original-tree.scions.git` (arbre Lepton complet, `scion/sys/…` et `scion/tools/…` à la
racine du dépôt, sans sous-chemin) et `lepton building *` → `$SCION_ROOTSTOCK/depots/generation/building`
(emplacement local créé par `rootstock-install`). La branche `master` du même seed décrit un
découpage plus fin (~18 scions sur `lepton-root.scions`) qui n'est pas utilisé ici mais reste
le cas de test de référence pour la greffe multi-scions à racine partagée.

L'outil fonctionne mais présente un défaut structurel et une dette qui le rendent inadapté à un
usage reproductible sous Linux / CI dans le cadre de la migration IAR → GCC :

1. **Pollution des dépôts.** `graft_scion()` lie des répertoires entiers ; quand deux scions
   partagent une racine (`sys/` pour kernel, lib, dev, bin…), le second est greffé *à l'intérieur du
   working tree du clone du premier*. Résultat dépendant de l'ordre, clones git sales,
   `ungraft` obligé de suivre les liens et de supprimer tout lien rencontré dans les dépôts.
2. **Bugs** : variable locale masquant la globale `rootstock_trunk_dir` dans
   `scion_rootstock_install()` (branche layout Lepton inatteignable, `UnboundLocalError` latent) ;
   `graft_update()` réutilise `location_grafted` résiduel d'une boucle précédente ;
   `get_scion_location()` retourne `None` sur `IOError` ; listes globales jamais vidées.
3. **Inexploitable en script** : erreurs terminées par `exit(0)`, `except:` nu, sortie de debug
   par `print`, `os.system`/`shell=True` sur des chaînes concaténées.
4. **Code mort / commandes annoncées non implémentées** : `seed-tag`, `graft-add/remove/replace/
   refresh`, `scion_rootstock_change`, `write/remove_ramification`, fichiers `~/.scion.settings/`
   écrits mais jamais relus.
5. `git pull` exécuté une fois par scion, donc ~18 fois sur le même clone.

Objectif de l'étape : **réécrire l'outil court (cible 300–400 lignes), iso-fonctionnel sur les
formats de fichiers et les commandes réellement utilisées, avec greffe par feuilles, codes de
retour corrects et tests.** Ce n'est pas une étape de la migration Lepton proprement dite : elle
vit dans le dépôt `seed.scions` et n'a pas de dépendance sur `MIGRATION-STATUS.md`.

Principe directeur : *les formats des fichiers `.scion.*` font foi*. La seule modification de
contenu autorisée sur un seed existant est la correction du chemin `$SCION_ROOTSTOCK/…` (décision
actée ci-dessous).

## Décisions actées

| Sujet | Décision |
|---|---|
| Langage / version | Python ≥ 3.10, bibliothèque standard uniquement (pas de dépendance PyPI) |
| Formats `.scion.ramifications`, `.scion.sources.list`, `.scion.grafted.list` | Conservés à l'identique (colonnes séparées par espaces/tabulations, `#` commentaire) |
| Nommage `shelf@prefix::suffix`, versions `master`, `?` (plus récente), `*` (locale) | Conservés |
| Layout rootstock (`depots/<shelf>/<prefix>/<version>`, trunk, signature) | Conservé |
| Greffe | Répertoires du trunk = vrais répertoires ; **seules les feuilles (fichiers) sont des liens symboliques relatifs** ; le trunk est jetable |
| Plateforme | Linux (et macOS). Le contournement Windows `CreateSymbolicLinkW` est supprimé |
| Fichier de settings `~/.scion.settings/` | Supprimé (jamais relu par l'outil actuel) — détection du rootstock par remontée depuis le cwd jusqu'à `.scion.rootstock.signature` |
| Variable d'environnement `SCION_ROOTSTOCK` | **Supprimée.** Le rootstock est le répertoire contenant `.scion.rootstock.signature` ; tout chemin local est résolu par rapport à lui. L'outil ne lit ni n'écrit aucune variable d'environnement |
| Chemins locaux dans `.scion.sources.list` | Un chemin relatif est relatif au rootstock (`depots/generation/building`) ; un chemin absolu est accepté tel quel. **L'ancienne forme `$SCION_ROOTSTOCK/…` est une erreur** (message explicite indiquant la correction attendue) ; aucune reconnaissance du préfixe, aucune expansion d'environnement |
| Correction du seed | `lepton-seed.scions`, branche `original-tree` : remplacer `$SCION_ROOTSTOCK/depots/generation/building` par `depots/generation/building` dans `.scion.sources.list` — un commit sur cette branche, hors du dépôt `seed.scions`. La branche `master` du seed n'est pas modifiée (hors périmètre) |
| Nom du trunk par défaut | `trunk` (option `--trunk` de `rootstock-install` conservée). La constante `tauon` disparaît |
| Généricité | L'outil est un gestionnaire d'arbre de sources générique, **pas un outil Lepton** : aucune chaîne `lepton`, `tauon`, aucun chemin Lepton en dur dans `scion/` ; tout ce qui est propre à Lepton vit dans les seeds. Le docstring du paquet (« graft scions on a lepton tree ») est reformulé |
| Branches | Outil : branche `rewrite/scion-0.5` sur `seed.scions`, fusion après validation. Arbre Lepton : le scion `original::tree` reste sur `master` de `lepton-original-tree.scions` ; les branches et tags de portage seront créés par les étapes de migration quand elles en auront besoin, pas par cette étape |
| Seed Lepton | `lepton-seed.scions`, branche `original-tree` : `scion seed-add --version original-tree https://github.com/lepton-distribution/lepton-seed.scions.git` ; clone attendu dans `depots/lepton-seed.scions/original-tree` |
| Layout créé par `rootstock-install` | Layout « générique » : `depots/generation/building/scion/building/{projects,staging/lib,output}` et `depots/origin/scion/sources`. C'est celui que le seed `original-tree` référence ; la branche de code « layout Lepton » (`depots/lepton/building/scion/sys/root/src/kernel/core/arch/…`) est supprimée |

| Commandes | `version`, `rootstock-information`, `rootstock-install`, `seed-add`, `seed-clone`, `seed-update`, `graft`, `ungraft`, `graft-clean`, `graft-update`, `git`. Supprimées : `seed-list`, `seed-tag` ; les `graft-add/remove/replace/refresh` de l'en-tête de l'ancien script ne sont pas implémentées |

Toutes les décisions sont actées : aucun `<À CONFIRMER>` ne subsiste. Si une question nouvelle
apparaît en cours de tâche, s'arrêter et demander plutôt que de trancher.

## Prérequis

- Clone de `seed.scions` (branche de travail dédiée : `rewrite/scion-0.5`).
- Clone de `lepton-seed.scions` (branche `original-tree`) et accès réseau à
  `lepton-original-tree.scions` (~4 800 fichiers ; ou un miroir local) pour le test d'intégration. Les tests unitaires ne doivent PAS exiger le réseau.
- `git ≥ 2.30`, `python3 ≥ 3.10`, `pytest`.
- Ne pas modifier `scion/scion.py` en place : la réécriture se fait dans un nouveau module
  (`scion/cli.py` + modules internes), l'ancien fichier est conservé comme oracle jusqu'à la
  validation puis supprimé au dernier commit.

## Tâches

### 0. Baseline et fixture de test

- Construire un **rootstock de test local** sans réseau : deux ou trois faux dépôts git dans
  `tests/fixtures/`, créés par un script (pas de `.git` versionné), reproduisant le cas critique :
  deux scions partageant la racine `sys/` (ex. `kernel/scion/sys/root/src/kernel/...` et
  `lib/scion/sys/root/src/lib/...`), un scion local versionné `*` en chemin relatif au rootstock
  (`depots/generation/building`) et un second avec l'ancienne forme `$SCION_ROOTSTOCK/...`
  (attendu : erreur explicite), un scion
  avec version `?`, un fichier en conflit entre deux scions.
- Un seed de test avec `.scion.ramifications` et `.scion.sources.list` copiés du **format** de
  `lepton-seed.scions` (mêmes colonnes, tabulations, commentaires). Copier dans `tests/data/` les
  fichiers réels des deux branches (`original-tree` et `master`) : le premier est le cas nominal
  (un scion distant sans sous-chemin + un scion local `*`), le second le cas multi-scions. Dans
  ces copies, corriger le chemin `$SCION_ROOTSTOCK/…` en chemin relatif ; conserver une ligne
  non corrigée dans un fichier séparé pour le test d'erreur.
- Exécuter l'ancien `scion.py` sur cette fixture et **capturer** : le `.scion.grafted.list` produit
  et la liste des chemins réels du trunk (`find trunk -exec readlink -f`). C'est l'oracle de
  non-régression pour le contenu logique de l'arbre (pas pour la forme des liens, qui change
  volontairement).

### 1. Structure du nouveau module

- `scion/model.py` : `@dataclass(frozen=True)` pour `ScionRef(shelf, prefix, suffix, version)`,
  `SourceEntry(ref, location, subpath)`, `GraftedEntry(ref, local_path, seed_dot_scion)`.
  Propriété `key = f"{shelf}/{prefix}::{suffix}"`. Parsing/sérialisation dans ce module, avec
  des tests sur les lignes réelles de `lepton-seed.scions`.
- `scion/rootstock.py` : découverte du rootstock (remontée depuis `Path.cwd()` jusqu'au premier
  répertoire contenant `.scion.rootstock.signature`, ou `rootstock_path` explicite), chemins
  dérivés (`depots`, `trunk`, `grafted_list`) et `resolve(local_path)` : chemin absolu inchangé,
  chemin relatif joint au rootstock, jamais d'`expandvars`. `Rootstock` est passé explicitement
  à toutes les fonctions ; aucun état global, aucune lecture/écriture de `os.environ`.
- `scion/gitops.py` : toutes les invocations git via `subprocess.run([...], check=True,
  cwd=...)`, jamais de chaîne shell. Fonctions `clone(url, dest, branch, single_branch)`,
  `checkout(dest, rev)`, `pull(dest)`, `run(dest, args)`.
- `scion/graft.py` : résolution ramification × sources → grafted list ; greffe ; dégreffe.
- `scion/cli.py` : `argparse` avec sous-commandes ; `main()` retourne un code de sortie.
- `logging` (niveaux INFO par défaut, DEBUG avec `-v`), aucun `print` hors sortie utilisateur.
- Toute erreur utilisateur → exception dédiée `ScionError` attrapée dans `main()` → message sur
  stderr, code de retour 1. Erreur git → code 2.

### 2. Résolution des sources (iso-fonctionnel)

Reproduire exactement la sélection actuelle de `get_scion_location()` :
- version explicite → entrée correspondante ;
- version `?` → entrée de version la plus élevée selon le comparateur de versions actuel
  (réimplémenter `compare()`/`_preprocess()` avec une regex raw string ; conserver le comportement
  numérique/alphabétique) ;
- `location` sans netloc → chemin local résolu par `Rootstock.resolve()` (relatif au rootstock) ;
  toute occurrence de `$` dans un chemin local → `ScionError` « variable d'environnement non
  supportée, utiliser un chemin relatif au rootstock » ;
- `subpath` optionnel ajouté au chemin local du dépôt.

Le chemin local d'un scion distant reste `depots/<shelf>/<prefix>/<version>`. Dans
`.scion.grafted.list`, écrire les chemins locaux **relatifs au rootstock** (l'outil actuel y écrit
des chemins absolus) : le rootstock devient déplaçable et la grafted list versionnable.

### 3. Clonage et mise à jour dédupliqués

- Regrouper les entrées par `(url, version)` avant `clone`/`pull` : un seul `pull` par clone.
- Reproduire la sémantique `--single_branch` actuelle : sans l'option, clone complet puis
  `checkout <version>` si ≠ `master` ; avec l'option, `clone -b <version> --single-branch`.
- Après clone, vérifier la présence de `<subpath>/scion/` dans le dépôt ; sinon `ScionError`
  explicite (aujourd'hui l'erreur n'apparaît qu'à la greffe).

### 4. Greffe par feuilles

- `graft(rootstock)` : lire `.scion.grafted.list` ; pour chaque entrée, parcourir
  `<local_path>/scion/` avec `os.walk(followlinks=False)` en ignorant `.scion/` ; pour chaque
  répertoire, `trunk/<rel>.mkdir(parents=True, exist_ok=True)` ; pour chaque fichier, créer
  `trunk/<rel>` → lien symbolique **absolu** vers le fichier source.
- Conflit (un fichier déjà présent dans le trunk, lien ou non) → collecter tous les conflits,
  les lister avec les deux origines, puis échouer (code 1) **sans laisser un trunk partiel** :
  dégreffer avant de sortir. Pas de règle « premier arrivé gagne » silencieuse.
- `ungraft(rootstock)` : supprimer le contenu du trunk **sans jamais suivre un lien** ; préserver
  `.scion.grafted.list`. Refuser de dégreffer si le trunk contient un fichier régulier non
  lien (donnée utilisateur) — le signaler et échouer, sauf option `--force`.
- Liens symboliques **relatifs** (`os.path.relpath` de la source par rapport au répertoire du
  lien) : cohérent avec la suppression de toute référence absolue au rootstock ; un rootstock
  déplacé ou monté à un autre chemin (conteneur) reste valide sans regreffer.
- Après greffe, vérifier qu'aucun clone dans `depots/` n'a été modifié (`git status --porcelain`
  vide sur la fixture) : c'est le test central de l'étape.

### 5. Interface en ligne de commande

- Sous-commandes : exactement la liste du tableau « Décisions actées », mêmes arguments que
  l'ancien script pour chacune ;
  `--single_branch` accepte aussi `--single-branch`.
- `rootstock_path` positionnel optionnel partout, défaut = rootstock découvert depuis le cwd ;
  message clair si aucun rootstock n'est trouvé.
- `git --key shelf@prefix::suffix --args "..."` : découper `--args` avec `shlex.split`.
- Aide de chaque sous-commande rédigée en termes génériques (rootstock, seed, scion, trunk),
  sans exemple Lepton ; les exemples Lepton vont dans le README, section « Exemple : arbre Lepton ».
- `version` affiche la version lue depuis `scion/__init__.py` (une seule source de vérité :
  supprimer `STR_SCION_TOOL_VERSION`). Passer `__version__` à `0.5.0`.

### 6. Tests

- `tests/test_seed.py` : le seed `original-tree` corrigé est reconnu ; l'ancienne forme est
  rejetée avec le message attendu.
- `tests/test_model.py` : parsing des lignes réelles de `lepton-seed.scions` (copier les deux
  fichiers dans `tests/data/`), tabulations multiples, commentaires, ligne incomplète ignorée,
  comparateur de versions (`1.0` vs `beta13`, `1.1.beta1` vs `1.1.beta2`, `*`, `master`).
- `tests/test_graft.py` sur la fixture de la tâche 0 : arbre greffé identique à l'oracle
  (ensemble des chemins réels résolus) ; dépôts propres après greffe ; conflit détecté et trunk
  vide après échec ; `ungraft` ne touche pas aux dépôts ; ordre des entrées sans effet (rejouer
  avec la grafted list inversée).
- `tests/test_cli.py` : codes de retour (0 succès, 1 erreur utilisateur, 2 erreur git),
  découverte du rootstock depuis un sous-répertoire.
- Test d'intégration optionnel, marqué `@pytest.mark.network` : `rootstock-install` dans un
  répertoire temporaire, `seed-add --version original-tree` du seed réel, `graft`, puis vérifier
  la présence de `trunk/sys/root/src`, `trunk/tools/bin/mklepton_gnu` et
  `trunk/building/projects`, et `git status --porcelain` vide dans
  `depots/lepton/original/master`.

### 7. Packaging et nettoyage

- Remplacer `setup.py` par `pyproject.toml` (`[project.scripts] scion = "scion.cli:main"`),
  `requires-python = ">=3.10"`. Supprimer `requirements.txt` vide et `MANIFEST.in` si inutiles.
- Supprimer `scion/scion.py` (ancien) au dernier commit, après validation des tests.
- Renseigner `CHANGELOG.md` (actuellement vide) : entrée 0.5.0 listant les ruptures :
  greffe par feuilles, suppression Windows, suppression `~/.scion.settings/`, commandes retirées.
- README : synopsis des commandes, description des trois formats de fichiers, schéma du layout
  rootstock, puis une section distincte « Exemple : arbre Lepton » avec la séquence
  `rootstock-install` → `seed-add --version original-tree …` → `graft`. Pas de recopie de l'en-tête de commentaires de l'ancien script.

## Critères de validation

- [ ] `pytest` vert sans réseau ; test `network` vert au moins une fois sur `lepton-seed.scions`
  branche `original-tree`.
- [ ] Sur la fixture : ensemble des chemins réels du trunk identique à l'oracle de la tâche 0.
- [ ] `git status --porcelain` vide dans chaque clone de `depots/` après `graft` puis `ungraft`.
- [ ] Greffe rejouée avec la grafted list dans l'ordre inverse → trunk identique.
- [ ] `grep -rni "lepton\|tauon" scion/` ne retourne rien ; les seeds de test Lepton ne sont
  référencés que depuis `tests/`.
- [ ] Aucun `print` hors `cli.py` ; aucun `shell=True` ; aucun `except:` nu ; aucune variable
  globale mutable de module.
- [ ] `scion <cmd>` retourne un code non nul sur chaque cas d'erreur listé en tâche 1.
- [ ] `wc -l scion/*.py` ≤ ~450 lignes hors tests (indicatif, pas un objectif à atteindre en
  sacrifiant la lisibilité).
- [ ] Fichiers `.scion.*` de `lepton-seed.scions` (`original-tree`) utilisés sans autre
  modification que la correction du chemin `building`.
- [ ] `python -W error -c "import scion.cli"` sans avertissement (regex, syntaxe).
- [ ] `grep -rn "SCION_ROOTSTOCK\|os.environ\|expandvars" scion/` ne retourne rien (le libellé
  du message d'erreur peut citer la variable ; le vérifier à la main).
- [ ] Commit de correction de `.scion.sources.list` poussé sur `original-tree` de
  `lepton-seed.scions` ; le test `network` tourne contre cette révision.
- [ ] Rootstock greffé, déplacé (`mv`), puis `find trunk -xtype l` vide : tous les liens restent
  valides sans regreffe ; `graft` rejoué depuis un sous-répertoire quelconque du rootstock déplacé
  produit le même arbre.

## Pièges connus

- Les fichiers `.scion.*` mélangent espaces et tabulations en nombre variable ; certaines lignes
  ont une colonne « chemin dans le dépôt » absente. Normaliser avec `str.split()` sans argument.
- La version `*` (scion `building`) désigne un emplacement local non versionné ; ne pas tenter de
  `clone`/`pull`.
- L'outil actuel positionne `SCION_ROOTSTOCK` dans `os.environ`, donc les sous-processus lancés
  par `scion git` en héritaient. Vérifier qu'aucun script ou hook des dépôts Lepton n'en dépend
  (`grep -r SCION_ROOTSTOCK` dans `lepton-original-tree.scions`, `lepton-seed.scions`, scripts de build) ;
  si c'est le cas, le signaler au commanditaire plutôt que de réintroduire la variable.
- Un `rootstock_path` explicite passé en argument doit lui aussi contenir
  `.scion.rootstock.signature` ; sinon erreur. Ne jamais déduire un rootstock d'un autre indice
  (présence de `depots/`, de la grafted list…).
- Liens relatifs : les calculer à partir du répertoire **du lien** dans le trunk, pas du
  rootstock ; tester avec un trunk à plusieurs niveaux de profondeur.
- CMake : `file(GLOB_RECURSE)` ne suit pas les répertoires liés, mais avec la greffe par feuilles
  tous les répertoires sont réels ; les fichiers liés sont vus normalement. Les messages du
  compilateur montreront le chemin du trunk, `realpath` donnera le chemin dans `depots/` — les
  deux sont valides.
- Un scion peut légitimement contenir des liens symboliques versionnés dans son dépôt : la greffe
  ne doit pas les résoudre (`followlinks=False`) et doit les recopier tels quels comme liens
  (`os.readlink` → `symlink`) ou, plus simple, les traiter comme des feuilles liées.
- L'ancien `ungraft` supprimait des liens **dans les dépôts** : si un rootstock existant a été
  greffé avec l'ancien outil, exécuter l'ancien `ungraft` une dernière fois avant de basculer,
  puis vérifier `git status` dans chaque clone.
- Ne pas « améliorer » le comparateur de versions ni les formats au passage : iso-fonctionnel.
- Le scion `original::tree` n'a pas de colonne « chemin dans le dépôt » : `scion/` est à la racine
  du clone. Le parseur doit accepter la colonne absente (déjà prévu) et la greffe doit partir de
  `<clone>/scion/`, pas de `<clone>/<vide>/scion/`.
- `lepton-original-tree.scions` contient des binaires Windows (`mklepton.exe`, `msvcr100d.dll`)
  et `mklepton_gnu` : hors périmètre de cet outil, mais leur présence dans le trunk est normale ;
  ne pas les filtrer.
- Le chantier de migration (`ETAPE-2`) porte `mklepton` nativement Linux : vérifier que ses
  chemins d'accès à l'arbre traversent le trunk et non `depots/` en dur.

## À la fin de l'étape

- Point d'arrêt : le commanditaire relit la CLI et valide la liste finale des commandes, puis
  fusion de `rewrite/scion-0.5` et tag `v0.5.0` sur `seed.scions`.
- Reporter dans le README du dépôt la procédure de migration d'un rootstock existant (paragraphe
  « Pièges connus », dernier point).
- Ajouter dans `doc/migration/MIGRATION-STATUS.md` la version épinglée de `scion` et la séquence
  de reconstitution de l'arbre : `rootstock-install` → `seed-add --version original-tree …` →
  `graft`. Cette séquence devient un prérequis de l'étape 1 de la migration.
