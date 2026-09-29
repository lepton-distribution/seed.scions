# scion

`scion` compose un **arbre de sources unique** à partir de sous-arbres issus de
plusieurs dépôts git. C'est un outil générique : rien de ce qu'il connaît n'est
propre à un projet donné, tout est décrit par des fichiers texte versionnés.

Le vocabulaire est celui de la greffe :

| terme | sens |
|---|---|
| **rootstock** (porte-greffe) | le répertoire de travail, reconnu par `.scion.rootstock.signature` |
| **depots/** | les clones git, jamais modifiés par l'outil |
| **scion** (greffon) | un sous-arbre d'un dépôt, sous un répertoire `scion/` |
| **trunk** | l'arbre composé, jetable, reconstruit à volonté |
| **seed** (semis) | un dépôt qui décrit quels scions composent l'arbre |

La greffe se fait **par feuilles** : chaque répertoire du trunk est un vrai
répertoire, chaque fichier est un lien symbolique *relatif* vers le fichier
d'origine dans `depots/`. Deux scions peuvent donc partager une racine sans que
l'un écrive dans le clone de l'autre, et le rootstock peut être déplacé ou monté
ailleurs (conteneur) sans regreffer.

Python ≥ 3.10, bibliothèque standard uniquement. Linux et macOS.

## Installation

```sh
pip install .
```

## Commandes

```
scion version                         affiche les versions
scion rootstock-information           affiche le rootstock courant et son trunk
scion rootstock-install [--trunk NOM] initialise le répertoire courant (vide)
scion seed-add [--version BRANCHE] [--single-branch] URL|CHEMIN
                                      ajoute un seed et clone ses scions
scion seed-clone  [--seed CHEMIN] [--single-branch]
                                      clone les scions d'un seed déjà présent
scion seed-update [--seed CHEMIN]     met à jour les clones d'un seed
scion graft                           (re)greffe le trunk
scion ungraft [--force]               vide le trunk
scion graft-clean [--force]           vide le trunk et oublie la liste greffée
scion graft-update                    met à jour tous les seeds puis regreffe
scion git --key shelf@prefix::suffix --args "..."
                                      exécute git dans le dépôt d'un scion
```

Toutes les commandes acceptent un `rootstock_path` en argument positionnel ; par
défaut l'outil remonte depuis le répertoire courant jusqu'au premier répertoire
portant `.scion.rootstock.signature`. `--trunk` nomme le trunk lorsqu'il y en a
plusieurs. `-v` passe le journal en mode détaillé.

Codes de retour : `0` succès, `1` erreur d'utilisation ou de configuration,
`2` échec d'une commande git.

## Layout d'un rootstock

```
mon-arbre/
├── .scion.rootstock.signature     marque le rootstock (fichier vide)
├── depots/                        les clones git — jamais modifiés
│   ├── <shelf>/<prefix>/<version>/    un scion distant
│   ├── generation/building/           produit par rootstock-install
│   └── origin/scion/sources/          produit par rootstock-install
└── trunk/                         l'arbre composé, jetable
    ├── .scion.grafted.list        ce qui est greffé (marque le trunk)
    └── ...                        répertoires réels, fichiers = liens relatifs
```

## Les trois formats

Dans les trois fichiers, les colonnes sont séparées par un nombre quelconque
d'espaces et de tabulations, `#` ouvre un commentaire jusqu'à la fin de la ligne,
et une ligne comptant trop peu de colonnes est ignorée.

### `<seed>/scion/.scion/.scion.ramifications` — que greffer

```
shelf   prefix::suffix   version
```

`version` est un nom de branche ou de tag, `?` pour « la plus récente déclarée »,
`*` pour un emplacement local non versionné. Le suffixe `::suffix` est
facultatif. Le couple `shelf` + nom identifie le scion : une seule entrée par
couple dans l'arbre final.

### `<seed>/scion/.scion/.scion.sources.list` — où le trouver

```
shelf   prefix::suffix   version   emplacement   [chemin dans le dépôt]
```

`emplacement` est soit une URL git, soit un chemin local. Un chemin local
**relatif est relatif au rootstock**, un chemin absolu est pris tel quel ; les
variables d'environnement ne sont pas supportées et provoquent une erreur
explicite. La 5ᵉ colonne est facultative : sans elle, le `scion/` du greffon est
à la racine du dépôt.

Un scion distant est cloné dans `depots/<shelf>/<prefix>/<version>`. Plusieurs
scions peuvent donc partager un clone en ne différant que par leur 5ᵉ colonne :
le dépôt n'est alors cloné et mis à jour qu'une fois.

### `<rootstock>/<trunk>/.scion.grafted.list` — ce qui est greffé

```
shelf   prefix::suffix   version   chemin local   [.scion du seed d'origine]
```

Écrit par `seed-add`, `seed-clone` et `seed-update`, lu par `graft`. Les chemins
qui sont dans le rootstock y sont écrits relativement à lui : le fichier est
versionnable et le rootstock déplaçable.

## Utilisation

```sh
mkdir mon-arbre && cd mon-arbre
scion rootstock-install
scion seed-add https://exemple.org/mon-seed.git
scion graft
```

Ensuite `scion graft-update` remet à jour tous les dépôts et reconstruit le
trunk ; `scion ungraft` le vide sans toucher aux clones.

### Exemple : arbre Lepton

```sh
mkdir lepton && cd lepton
scion rootstock-install
scion seed-add --version original-tree \
      https://github.com/lepton-distribution/lepton-seed.scions.git
scion graft
```

On obtient `trunk/sys/`, `trunk/tools/` et `trunk/building/`, le tout composé
depuis `depots/lepton/original/master` (l'arbre Lepton) et
`depots/generation/building` (l'emplacement de génération créé par
`rootstock-install`).

## Migration d'un rootstock greffé par scion ≤ 0.4

Les versions antérieures liaient des **répertoires** entiers, ce qui amenait
l'outil à écrire des liens *à l'intérieur des clones* et `ungraft` à les y
supprimer. Avant de basculer :

1. avec l'**ancien** outil, exécuter `ungraft` une dernière fois ;
2. vérifier `git status` dans chaque clone de `depots/` et nettoyer ce qui
   reste (`git clean -nd` puis `-fd`) ;
3. corriger les `.scion.sources.list` des seeds : `$SCION_ROOTSTOCK/quelque/chose`
   devient `quelque/chose` ;
4. installer scion 0.5 et relancer `scion seed-update` puis `scion graft`.

La variable d'environnement `SCION_ROOTSTOCK` n'est plus ni lue ni positionnée :
si un script de build en dépendait, il la recevait de scion et ne la recevra
plus.

## Tests

```sh
python3 -m unittest discover -s tests          # sans réseau
pytest tests/                                  # identique, si pytest est installé
SCION_TEST_NETWORK=1 python3 -m unittest discover -s tests -p 'test_network.py'
```
