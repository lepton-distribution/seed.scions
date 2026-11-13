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

Ce que git ignore dans un clone (`.gitignore`, `.git/info/exclude`,
`core.excludesFile`) n'est pas greffé : deux clones qui portent le même fichier
ignoré au même chemin ne sont pas en conflit. Un fichier suivi l'est toujours,
même s'il correspond à une règle ; un fichier nouveau, non suivi et non ignoré,
l'est aussi. Un scion hors git suit les mêmes règles : ses propres fichiers
`.gitignore` et `core.excludesFile`, lus au travers d'un dépôt vide temporaire,
sans rien écrire dans la source. Un scion dont le dépôt contient le rootstock
lui-même n'est pas filtré. `-v` liste les chemins exclus.

Python ≥ 3.10, bibliothèque standard uniquement. Linux et macOS.

## Installation

`scion` est un outil en ligne de commande sans aucune dépendance : seule la
bibliothèque standard est utilisée. Le paquet déclare son point d'entrée dans
`pyproject.toml`, donc toute installation fournit la commande `scion`.

Les voies ci-dessous sont **exclusives** : elles déposent toutes une commande
nommée `scion`, généralement dans `~/.local/bin`, et la dernière appliquée
masque les précédentes. En cas de doute, `command -v scion` dit laquelle
répond et `scion version` confirme la version obtenue.

### pipx — recommandé

`pipx` place l'outil dans un environnement isolé et sa commande dans
`~/.local/bin`, sans toucher au Python du système. C'est aussi la seule voie
propre sur les distributions qui appliquent la [PEP 668][pep668] (Debian,
Ubuntu, Fedora récents), où `pip install` dans le Python système est refusé.

```sh
pipx install .            # depuis le dépôt cloné
pipx install /chemin/vers/seed.scions
```

Mise à jour après modification des sources — `pipx upgrade` ne sert à rien ici,
l'installation venant d'un chemin local et non d'un index :

```sh
pipx install --force /chemin/vers/seed.scions
```

Désinstallation : `pipx uninstall scion`.

[pep668]: https://peps.python.org/pep-0668/

### Mode éditable — pour développer

La commande exécute alors directement les sources du dépôt : toute modification
est prise en compte immédiatement, sans réinstaller.

```sh
pipx install --force --editable /chemin/vers/seed.scions
```

`scion` et `python3 -m scion.cli` ne peuvent alors plus diverger. Une
modification du `pyproject.toml` (point d'entrée, dépendances) demande en
revanche de rejouer la commande.

Cette installation dépose `build/` et `*.egg-info/` dans le dépôt ; ils sont
ignorés par `.gitignore` et peuvent être supprimés à tout moment, la commande
installée pointant directement sur `scion/`.

### venv et pip

```sh
python3 -m venv ~/.local/share/scion-venv
~/.local/share/scion-venv/bin/pip install /chemin/vers/seed.scions
ln -s ~/.local/share/scion-venv/bin/scion ~/.local/bin/scion
```

`pip install .` sans environnement virtuel ne convient que si le Python visé
n'est pas géré par la distribution.

### zipapp — un seul fichier, aucune installation

L'outil n'utilisant que la bibliothèque standard, `zipapp` (lui aussi dans la
bibliothèque standard) en fait un exécutable autonome d'une trentaine de
kilo-octets. Utile là où ni `pip` ni `pipx` ne sont disponibles, et pour
déposer l'outil dans une image de CI.

```sh
cd /chemin/vers/seed.scions
mkdir -p /tmp/scion-build && cp -r scion /tmp/scion-build/
printf 'import sys\nfrom scion.cli import main\nsys.exit(main())\n' \
    > /tmp/scion-build/__main__.py
python3 -m zipapp /tmp/scion-build -p "/usr/bin/env python3" -o ~/.local/bin/scion
chmod +x ~/.local/bin/scion
```

Le `__main__.py` explicite n'est pas facultatif : l'option `-m` de `zipapp`
engendre un lanceur qui ignore la valeur de retour de `main()`, ce qui
écraserait les codes de retour décrits plus bas.

Désinstallation : `rm ~/.local/bin/scion`.

### Sans rien installer

Depuis une copie du dépôt, `python3 -m scion.cli <commande>` est équivalent à
`scion <commande>`.

## Commandes

```
scion version                         affiche les versions
scion rootstock-information           affiche le rootstock courant et son trunk
scion rootstock-install [--trunk NOM] [--bare]
                                      initialise le répertoire courant (vide)
scion seed-add [--version BRANCHE] [--single-branch] URL|CHEMIN
                                      ajoute un seed et clone ses scions
scion seed-clone  [--seed CHEMIN] [--single-branch]
                                      clone les scions d'un seed déjà présent
scion seed-update [--seed CHEMIN]     avance un seed et met à jour ses clones
scion seed-scion-add [--seed CHEMIN] [--replace] shelf@prefix::suffix VERSION EMPLACEMENT [CHEMIN]
                                      déclare un scion dans un seed
scion seed-scion-remove [--seed CHEMIN] shelf@prefix::suffix
                                      retire un scion d'un seed
scion graft [--force] [--scion shelf@prefix::suffix ...]
                                      (re)greffe le trunk, ou un seul scion
scion graft-remove [--purge] [--force] shelf@prefix::suffix
                                      retire un scion du trunk (et son clone)
scion ungraft [--force]               vide le trunk
scion graft-clean [--force]           vide le trunk et oublie la liste greffée
scion graft-update                    avance tous les seeds et leurs clones, puis regreffe
scion mirror-sync [--seed CHEMIN] [--dry-run] [URL ...]
                                      avance les miroirs déclarés (avance rapide seulement)
scion git --key shelf@prefix::suffix --args "..."
                                      exécute git dans le dépôt d'un scion
```

Toutes les commandes qui agissent sur un rootstock acceptent un `rootstock_path`
en argument positionnel (après la clé pour `graft-remove`) ; par
défaut l'outil remonte depuis le répertoire courant jusqu'au premier répertoire
portant `.scion.rootstock.signature`. `--trunk` nomme le trunk lorsqu'il y en a
plusieurs. `-v` passe le journal en mode détaillé.

Codes de retour : `0` succès, `1` erreur d'utilisation ou de configuration,
`2` échec d'une commande git. `mirror-sync` : `1` dès qu'une référence est
signalée, `2` pour un miroir non déclaré donné en argument (ci-dessous).

## Layout d'un rootstock

```
mon-arbre/
├── .scion.rootstock.signature     marque le rootstock (fichier vide)
├── .scion.trunk.tolerated         fichiers tolérés dans le trunk (sauf --bare)
├── depots/                        les clones git — jamais modifiés
│   ├── <shelf>/<prefix>/<version>/    un scion distant
│   ├── generation/building/           produit par rootstock-install (sauf --bare)
│   └── origin/scion/sources/          produit par rootstock-install (sauf --bare)
└── trunk/                         l'arbre composé, jetable
    ├── .scion.grafted.list        ce qui est greffé (marque le trunk)
    └── ...                        répertoires réels, fichiers = liens relatifs
```

Un fichier régulier du trunk est une donnée de l'utilisateur, pas une greffe :
il bloque `ungraft`, `graft`, `graft-remove` et `graft-clean`, sauf `--force`,
qui le conserve et dégreffe le reste. Les fichiers créés par le système (index
d'un explorateur de fichiers, par exemple) se déclarent dans
`.scion.trunk.tolerated` : un motif `fnmatch` par ligne, appliqué au nom du
fichier, `#` en commentaire ; absent, rien n'est toléré.

```
.DS_Store
._*
```

Un fichier toléré ne bloque rien et disparaît avec le dégreffage : `ungraft` le
supprime, et `graft --scion` ou `graft-remove` le suppriment avec le répertoire
qu'ils retirent.

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
shelf   prefix::suffix   version   chemin local   [.scion du seed d'origine]   [.scion porteur]
```

Écrit par `seed-add`, `seed-clone` et `seed-update`, lu par `graft`. Les chemins
qui sont dans le rootstock y sont écrits relativement à lui : le fichier est
versionnable et le rootstock déplaçable. La 6ᵉ colonne n'existe que pour une
clé projetée déclarée par un scion porteur (ci-dessous).

## Projection d'un dépôt tiers (0.6.0.0)

Un dépôt qui n'a pas de répertoire `scion/` se greffe par **projection** : on
déclare quels de ses fichiers vont où dans le trunk. La spécification complète,
règle par règle, est dans [`doc/projection-miroir.md`](doc/projection-miroir.md)
(partie A).

La clé se déclare comme un scion ordinaire (sources et ramifications), et ses
lignes de projection vont dans `.scion.projections`, dans le même `.scion/` :

```
# .scion.sources.list
tiers   vendor-hal   v1.2.0   https://example.org/vendor-hal.git
# .scion.ramifications
tiers   vendor-hal   v1.2.0
# .scion.projections : shelf nom motif destination, ou shelf nom !motif
tiers   vendor-hal   Inc/**          scion/include/vendor/
tiers   vendor-hal   Src/*.c         scion/src/vendor/
tiers   vendor-hal   LICENSE.md      scion/include/vendor/
tiers   vendor-hal   !Src/legacy.c
```

- Les motifs portent sur les fichiers suivis par git au commit épinglé, jamais
  sur le disque : `d/**` (récursif), `d/*` ou `d/x_[ab]*.h` (jokers dans le
  dernier segment seulement), ou un chemin de fichier. `!motif` exclut.
- Une destination commence par `scion/` (la racine du trunk). Terminée par `/`,
  elle remplace la base du motif ; sans `/`, elle renomme un fichier.
- La version est un **tag** ou un **commit complet** (40 caractères) ; une
  branche, `*` et `?` sont refusés. Le clone est partiel
  (`--filter=blob:none`) et en `HEAD` détaché ; il doit rester à son commit et
  sans modification de fichier suivi, sinon la greffe est refusée.
- Depuis 0.6.3.0, un clone distant n'extrait que les répertoires parents des
  fichiers projetés, plus les fichiers de la racine et des répertoires ancêtres
  (`git sparse-checkout`, mode cône ; git ≥ 2.35). La greffe recalcule cet
  ensemble ; un clone extrait en entier est converti par sa prochaine greffe.
  Un fichier non projeté se lit par `git -C <clone> show HEAD:<chemin>`.
- Toute ligne mal formée, tout motif sans correspondance, toute collision de
  casse dans le trunk est une erreur (code 1), qui cite fichier et ligne.

Les lignes peuvent être dans la graine, ou dans le `scion/.scion/` d'un scion
ordinaire qui dépend du dépôt tiers : ce scion **porteur** emporte ses
projections partout où il est greffé. Un porteur ne déclare que des clés
projetées ; son `.scion/` n'est jamais greffé. `graft-remove <porteur>` retire
aussi ses projections ; une projection que le porteur ne déclare plus est
retirée à la synchronisation suivante.

Un rootstock sans aucun `.scion.projections` se comporte exactement comme en
0.5.4.0.

## Miroir de conservation (0.6.1.0)

Un **miroir** est un dépôt distant que l'on contrôle, copie d'un amont tiers,
et que les graines désignent à la place de l'amont : il garde les commits
épinglés même si l'amont disparaît, réécrit son historique ou déplace un tag.
Spécification : [`doc/projection-miroir.md`](doc/projection-miroir.md), partie B.

Les miroirs se déclarent dans un `.scion/` de graine ou de porteur, à côté de la
ligne de sources qui désigne le miroir :

```
# .scion.mirrors : <url du miroir> <url de l'amont>
https://example.org/mirrors/vendor-hal.git   https://example.org/vendor/vendor-hal.git
```

`scion mirror-sync` traite les miroirs des graines de la liste greffée et de
leurs porteurs (ou ceux d'une graine avec `--seed`, ou seulement les URL
données). Pour chacun, dans `depots/.mirrors/<hôte>/<chemin>` :

| Amont comparé au miroir | Action |
| --- | --- |
| branche ou tag absent du miroir | envoyé |
| branche en avance rapide | envoyée |
| identique | rien (`-v`) |
| branche réécrite, ou miroir en avance | **non envoyée**, signalée |
| tag déplacé (autre objet) | **non propagé**, signalé avec les deux commits |
| branche ou tag supprimé dans l'amont | conservé dans le miroir, signalé à chaque passe |

- Seules les branches et les tags sont traités. Chaque référence est envoyée
  par son nom, jamais `--force`, `--mirror`, `--prune` ni suppression : rien
  n'est jamais supprimé ni réécrit dans un miroir.
- scion ne crée aucun dépôt distant et ne règle aucune authentification : celle
  de git s'applique (par exemple
  `git config --global url."ssh://git@github.com/".pushInsteadOf "https://github.com/"`).
- `--dry-run` calcule et rapporte sans rien envoyer.
- Code `0` sans signalement, `1` avec au moins un signalement (miroir ou amont
  inaccessible compris) ou une déclaration incorrecte, `2` pour une URL non
  déclarée ou un échec git local.
- La greffe ne lit jamais `.scion.mirrors` pour choisir une URL ; quand le
  clonage d'un miroir ou sa version échoue, le message suggère
  `scion mirror-sync`.

## Utilisation

```sh
mkdir mon-arbre && cd mon-arbre
scion rootstock-install
scion seed-add https://exemple.org/mon-seed.git
scion graft
```

Ensuite `scion graft-update` remet à jour tous les dépôts et reconstruit le
trunk ; `scion ungraft` le vide sans toucher aux clones.

`graft-update` et `seed-update` avancent aussi le dépôt git de chaque seed, par
avance rapide sur son amont, avant de lire ses scions : un scion ajouté au seed
publié est donc cloné et greffé. Un seed qui a des modifications de fichiers
suivis, ou dont la branche a divergé, arrête la commande avant toute
modification (trunk intact). Un seed hors git, sans amont, ou dans le dépôt qui
contient le rootstock est laissé tel quel ; un seed seulement en avance sur son
amont aussi.

Les clones existants suivent la même règle, pour `graft-update`, `seed-update` et
`seed-add` : chacun est contrôlé avant toute modification, puis avancé par
`git fetch` et `git merge --ff-only @{u}` ; scion ne fait jamais de `git pull`.
Un clone qui n'est pas sur sa version déclarée (autre branche, `HEAD` détaché),
sans amont, divergé, ou en retard avec des modifications de fichiers suivis
arrête la commande ; le message nomme tous les clones concernés et la commande
de remise. Une version déclarée par un tag est vérifiée (`HEAD` sur le tag, tag
inchangé dans l'amont), jamais tirée.

Si la regreffe de `graft` ou de `graft-update` échoue (conflit, git), le trunk
est rétabli tel qu'il était (liens, répertoires, `.scion.grafted.list`) ; le
message le signale.

Un clonage en échec (scion, seed distant, clé projetée, dépôt de travail d'un
miroir) ne laisse aucun répertoire dans `depots/` : ceux que scion a créés pour
lui sont retirés s'ils sont vides (depuis 0.6.3.1 ; `-v` les nomme). Un
répertoire qui existait avant l'appel est gardé, de même qu'un clone réussi dont
la version est introuvable.

### Faire évoluer un seed

Aucune de ces commandes ne fait de `git pull` ; `seed-scion-*` n'éditent que
les deux fichiers du seed (à commiter dans son dépôt).

```sh
# ajouter un scion
scion seed-scion-add --seed S shelf@nom master https://exemple.org/depot.git
scion seed-clone --seed S
scion graft --scion shelf@nom

# retirer un scion (--purge : supprimer aussi son clone)
scion seed-scion-remove --seed S shelf@nom
scion graft-remove shelf@nom

# remplacer un scion (autre version ou autre dépôt)
scion seed-scion-add --seed S --replace shelf@nom v2 https://exemple.org/autre.git
scion graft-remove shelf@nom
scion seed-clone --seed S
scion graft --scion shelf@nom
```

Après la création ou la suppression d'un fichier dans un clone,
`scion graft --scion shelf@nom` regreffe ce seul scion.

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
