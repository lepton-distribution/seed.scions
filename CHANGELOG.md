# Journal des modifications

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
