# MIGRATION-STATUS — arbre Lepton, IAR → GCC

Suivi du chantier de migration. Ce fichier est la référence pour l'outillage
épinglé et pour la reconstitution de l'arbre de sources ; les étapes de
migration proprement dites s'y ajoutent au fur et à mesure.

Dernière vérification : **2026-09-29**.

## Outillage épinglé

| outil | version | dépôt | référence |
|---|---|---|---|
| `scion` | **0.5.0.1** | `lepton-distribution/seed.scions` | tag `0.5.0.1` = `54dc319` |

Prérequis : Python ≥ 3.10, git ≥ 2.30, Linux ou macOS. Aucune dépendance PyPI.
Windows n'est plus supporté depuis 0.5.0.1.

Installation :

```sh
git clone -b 0.5.0.1 https://github.com/lepton-distribution/seed.scions.git
pip install ./seed.scions
```

## Seed de référence

| | |
|---|---|
| dépôt | `lepton-distribution/lepton-seed.scions` |
| branche | `original-tree` |
| commit | `083c30b` — *remove the stale Python 2 copy of the scion tool* |

Il déclare deux scions : `lepton original::tree master` (l'arbre Lepton complet,
`scion/sys/` et `scion/tools/` à la racine du dépôt) et `lepton building *`
(emplacement de génération local, créé par `rootstock-install`).

La branche `master` du même seed décrit un découpage plus fin (20 scions) qui
**n'est pas utilisé par ce chantier**. Elle a reçu les mêmes corrections
(commit `f41a23f`) et se résout entièrement avec scion 0.5.0.1 : 20 scions pour
**3 clones** seulement (`lepton-root.scions`, `lepton-gnu.scions` et
`bitbucket.org/phlb/lepton-xgui.scions`), les 16 scions `root::*` ne différant
que par leur colonne « chemin dans le dépôt ». C'est le cas de test de référence
pour la greffe multi-scions à racine partagée.

Une réserve avant de s'en servir : son scion `building` pointe sur
`depots/lepton/building`, que `rootstock-install` **ne crée pas** — il produit
`depots/generation/building`. L'écart est antérieur à la migration : la branche
de l'ancien outil qui créait le layout Lepton était inatteignable, son option
`--trunk` valant toujours `trunk`. Il faudra soit créer ce répertoire, soit
repointer l'entrée.

## Prérequis de l'étape 1 — reconstitution de l'arbre

Séquence de référence, à rejouer telle quelle (CI comprise) :

```sh
mkdir lepton && cd lepton
scion rootstock-install
scion seed-add --version original-tree \
      https://github.com/lepton-distribution/lepton-seed.scions.git
scion graft
```

On obtient :

```
lepton/
├── .scion.rootstock.signature
├── depots/
│   ├── lepton/original/master/        clone de lepton-original-tree.scions
│   ├── lepton-seed.scions/original-tree/   clone du seed
│   ├── generation/building/           emplacement de génération
│   └── origin/scion/sources/
└── trunk/                             l'arbre composé
    ├── sys/    tools/    building/
    └── .scion.grafted.list
```

`scion graft-update` remet à jour les dépôts et reconstruit le trunk.
`scion ungraft` vide le trunk sans toucher aux clones.

### Vérifié le 2026-09-29, contre le seed publié

- **4829 feuilles greffées** (les 4832 fichiers du dépôt moins `.gitignore`,
  `LICENSE` et `README.md`, qui sont hors de `scion/`).
- `trunk/sys/root/src`, `trunk/tools/bin/mklepton_gnu` et `trunk/building/projects`
  présents ; les répertoires sont réels, les fichiers sont des liens relatifs.
- `git status --porcelain` **vide** dans `depots/lepton/original/master` après
  greffe : les clones ne sont plus pollués.
- `find trunk -xtype l` vide, y compris après déplacement du rootstock.

## Constats pour les étapes suivantes

### Le trunk doit s'appeler `tauon`, ou les mkconf doivent changer

Les configurations de build GCC codent en dur un chemin qui suppose le trunk
nommé `tauon` et placé dans `$HOME` :

```
$(HOME)/tauon/sys/root/src/kernel/core/arch/arm
$(HOME)/tauon/sys/user/tauon_sampleapp/etc
```

Concernés : `scion/tools/bin/mklepton_gnu.sh` (qui substitue `$(HOME)` par `sed`)
et quatre fichiers `scion/sys/user/tauon_sampleapp/etc/mkconf_tauon_sampleapp*.xml`.

Deux issues, à trancher par l'étape qui porte `mklepton` :

1. `scion rootstock-install --trunk tauon` dans `$HOME` — l'option `--trunk` est
   conservée en 0.5.0.1 et reproduit exactement l'arborescence attendue ;
2. rendre les chemins des mkconf relatifs au trunk plutôt qu'à `$HOME`, ce qui
   libère le nom et l'emplacement du rootstock (nécessaire pour la CI et les
   conteneurs).

La seconde est la bonne à terme ; la première débloque immédiatement.

### Aucun chemin `depots/` en dur — piège levé

`grep -rn "depots/"` sur l'arbre Lepton ne renvoie rien : aucun script ni
configuration n'atteint les clones directement. Tous les accès passent donc bien
par le trunk, ce que la greffe par feuilles rend possible sans copie.

### `SCION_ROOTSTOCK` : aucune dépendance dans l'arbre — piège levé

`grep -rn "SCION_ROOTSTOCK"` sur `lepton-original-tree.scions` ne renvoie rien.
Aucun script ni hook ne dépendait de la variable que l'ancien outil positionnait
dans l'environnement des sous-processus. Sa suppression en 0.5.0.1 est donc sans
effet sur les builds.

### Copie obsolète de l'outil dans le seed — supprimée

`lepton-seed.scions/scion/.scion/scion.py` était une copie Python **2** de scion
(711 lignes, `from urlparse import urlparse`, `print` sans parenthèses — elle ne
s'analysait même pas sous Python 3). Elle n'était lue par rien : l'outil ne lit
que `.scion.ramifications` et `.scion.sources.list` dans ce répertoire. Retirée
des deux branches du seed pour qu'on ne la prenne pas pour l'implémentation de
référence, qui vit dans `lepton-distribution/seed.scions`.

### Binaires Windows présents dans l'arbre

`scion/tools/bin/mklepton.exe`, `msvcr100d.dll` et `scion/tauon_make_link.bat`
sont versionnés dans l'arbre et se retrouvent donc dans le trunk. C'est normal et
hors périmètre de `scion`, qui ne filtre rien. `mklepton_gnu` est le binaire à
remplacer par une version native Linux.

## Étapes

| étape | objet | état |
|---|---|---|
| 0 | outillage `scion` : réécriture, greffe par feuilles, tests | **terminée** — tag `0.5.0.1` |
| 1 | reconstitution de l'arbre (prérequis ci-dessus) | prête à démarrer |
| 2 | `mklepton` natif Linux | à renseigner |
| … | | à renseigner |

Le détail des étapes 2 et suivantes n'est pas encore écrit : ce tableau ne liste
que ce qui est établi.
