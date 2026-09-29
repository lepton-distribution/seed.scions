# Journal des modifications

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
