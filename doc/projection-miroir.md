# scion — projection d'un dépôt tiers et miroir de conservation

Spécification. Aucune ligne de code ne la précède. Elle décrit deux évolutions indépendantes :

- **A. Projection** : greffer un dépôt qui n'a pas de répertoire `scion/`, en déclarant quels
  fichiers vont où.
- **B. Miroir de conservation** : tenir à jour, par avance rapide seulement, une copie d'un dépôt
  tiers que l'on contrôle, et y faire pointer les graines.

Versions : la première des deux livrée est **0.6.0.0**, la seconde **0.6.1.0**. Chaque règle porte un
identifiant (`P-…`, `M-…`) repris par le plan de tests.

## 0. Vocabulaire

| Terme | Sens |
| --- | --- |
| dépôt tiers | dépôt git qui n'a pas la structure d'un scion (pas de `scion/`) |
| clé projetée | clé `shelf/nom` qui a au moins une ligne dans un `.scion.projections` |
| `.scion/` porteur | répertoire `.scion/` qui déclare des clés projetées : celui d'une graine, ou celui d'un scion (§A.9) |
| liste git | les fichiers suivis par git au commit épinglé (`git ls-tree -r <commit>`), chemins exacts, casse comprise |
| base d'un motif | le répertoire du dépôt tiers que le motif parcourt (§A.3) |
| miroir | dépôt git distant, copie d'un amont, mis à jour par `mirror-sync` |

## 1. Compatibilité

- **P-C1.** Un rootstock dont aucune graine et aucun scion greffé n'a de `.scion.projections` ni de
  `.scion.mirrors` se comporte exactement comme en 0.5.4.0 : mêmes liens, mêmes messages, mêmes codes
  de retour, même `.scion.grafted.list`.
- **P-C2.** Les formats existants (`.scion.sources.list`, `.scion.ramifications`,
  `.scion.grafted.list`, `.scion.trunk.tolerated`) ne changent pas de sens. `.scion.grafted.list`
  gagne une 6ᵉ colonne facultative (§A.9), absente quand elle serait égale à la 5ᵉ.
- **P-C3.** Un scion ordinaire dont `scion/.scion/` n'a pas de `.scion.projections` n'est pas un
  porteur : son `.scion/` reste ignoré, comme en 0.5.4.0.

## A. Projection

### A.1 Déclaration

- **P-D1.** Un dépôt tiers se déclare comme un scion ordinaire : une ligne dans `.scion.sources.list`
  (`shelf nom version emplacement`) et une dans `.scion.ramifications` (`shelf nom version`), dans le
  même `.scion/`.
- **P-D2.** Une clé est **projetée** si le `.scion.projections` de ce `.scion/` a au moins une ligne
  d'inclusion pour elle. Elle est alors greffée par ses lignes de projection, jamais par un
  répertoire `scion/` ; la 5ᵉ colonne de `.scion.sources.list` (chemin dans le dépôt) est refusée
  pour une clé projetée.
- **P-D3.** Une ligne de `.scion.projections` dont la clé n'a pas de ligne de sources et de
  ramifications dans le même `.scion/` est une erreur.

### A.2 Format de `.scion.projections`

Mêmes règles lexicales que les autres fichiers : champs séparés par des espaces ou des tabulations,
`#` ouvre un commentaire, lignes vides ignorées. Deux formes de ligne :

```
<shelf>  <nom>  <motif>   <destination>     # inclusion
<shelf>  <nom>  !<motif>                    # exclusion
```

- **P-F1.** Contrairement aux fichiers historiques, une ligne non vide qui n'a pas exactement 4
  champs (inclusion) ou 3 champs commençant par `!` (exclusion) est une **erreur** qui cite le fichier
  et le numéro de ligne. Rien n'est ignoré en silence.
- **P-F2.** Un chemin ne peut contenir ni blanc ni `#` (limite des fichiers en colonnes).

### A.3 Motifs

Un motif est un chemin relatif à la racine du dépôt tiers, segments séparés par `/`.

| Forme | Exemple | Désigne | Base |
| --- | --- | --- | --- |
| fichier | `docs/LICENSE.txt` | ce fichier | son répertoire (`docs`) |
| non récursif | `include/*` | les fichiers directement sous `include/` | `include` |
| filtre | `include/vendor_[ab]1*.h` | les fichiers directement sous `include/` dont le nom correspond | `include` |
| récursif | `src/**` | tous les fichiers sous `src/`, à toute profondeur | `src` |
| récursif, racine | `**` | tous les fichiers du dépôt | racine |

- **P-M1.** Jokers `*`, `?`, `[…]` (sens de `fnmatch`, sensibles à la casse), seulement dans le
  **dernier** segment ; ils ne franchissent pas `/`. `*` correspond aussi aux noms qui commencent par
  un point.
- **P-M2.** `**` n'est admis que comme dernier segment entier (`d/**` ou `**`).
- **P-M3.** Interdits : `/` initial ou final, segment vide, `.` ou `..`.
- **P-M4.** Les motifs portent sur la **liste git** du commit épinglé, jamais sur le disque. Un
  fichier non suivi n'est jamais désigné. Un sous-module (entrée de type commit) n'est pas un
  fichier : il n'est jamais désigné, et la forme fichier qui le nomme est une erreur. Un lien
  symbolique suivi par git est un fichier : il est projeté comme une feuille, jamais suivi.
- **P-M5.** La forme fichier qui nomme un répertoire de la liste git est une erreur (« utilisez
  `d/*` ou `d/**` »).

### A.4 Destinations

- **P-T1.** Une destination commence par `scion/`. Ce préfixe représente la racine du trunk et
  n'y figure pas : `scion/include/` désigne le répertoire `include/` du trunk.
- **P-T2.** Destination terminée par `/` : un répertoire. Chaque fichier désigné y est placé
  avec son chemin **relatif à la base du motif**. La base est ainsi renommée en la destination :
  `Include/*` → `scion/inc/` place `Include/a.h` en `inc/a.h`.
- **P-T3.** Destination sans `/` final : un fichier. Admise seulement pour la forme fichier (le
  fichier est alors renommé). Pour les autres formes, c'est une erreur.
- **P-T4.** Interdits dans une destination : segment vide, `.`, `..`, segment `.scion`, et le chemin
  `scion/.scion.grafted.list`. La règle vaut aussi pour chaque chemin du trunk calculé (destination
  et chemin relatif à la base) : un fichier amont placé sous un répertoire `.scion/`, ou projeté en
  `.scion.grafted.list` à la racine du trunk, est une erreur qui nomme la ligne et le fichier.

### A.5 Exclusions

- **P-X1.** Une ligne `!motif` retire, de **toutes** les inclusions de la même clé, les fichiers
  qu'elle désigne, quel que soit l'ordre des lignes. Même grammaire qu'un motif (§A.3).
- **P-X2.** Une exclusion porte sur les fichiers source, pas sur les destinations.

### A.6 Résolution d'une clé

Pour une clé projetée, scion calcule l'ensemble des couples (fichier source, chemin du trunk).

- **P-R1.** Une inclusion qui ne désigne aucun fichier de la liste git est une **erreur**.
- **P-R2.** Une exclusion qui ne désigne aucun fichier retenu par les inclusions de la clé est une
  **erreur**.
- **P-R3.** Même source vers même chemin du trunk par deux lignes : un seul lien, sans message.
- **P-R4.** Deux sources différentes vers le même chemin du trunk : **erreur**, qui nomme les deux
  lignes.
- **P-R5.** Une même source vers deux chemins du trunk : deux liens.
- **P-R6.** Un chemin du trunk qui est à la fois un fichier projeté et un répertoire (projeté ou
  non) est une erreur.

Toutes les erreurs d'une clé sont collectées avant d'être signalées ; aucune n'est signalée au
fil de l'eau.

### A.7 Casse

- **P-K1.** Les motifs sont comparés avec la casse exacte de la liste git, sur tout système.
- **P-K2.** Après résolution de tous les scions, deux chemins du trunk distincts qui ne diffèrent
  que par la casse (comparaison sur chaque segment, répertoires compris), dont l'un au moins vient
  d'une projection, sont une **erreur sur tout système**, que le système de fichiers distingue ou
  non la casse. Un rootstock qui greffe sur l'un greffe ainsi sur l'autre. Exemple : une projection
  vers `scion/inc/` et un scion ordinaire qui fournit `Inc/b.h`. Les segments sont comparés par
  `str.casefold()`. `graft --scion` compare aussi aux chemins déjà présents dans le trunk.

### A.8 Version épinglée, clone, état du clone

- **P-V1.** La version d'une clé projetée est un **tag** ou un **commit complet** (40 caractères
  hexadécimaux ; une version de cette forme est toujours lue comme un commit). Une branche, `*` et
  `?` sont refusés pour une clé projetée. Tag et branche ne se distinguent qu'une fois le dépôt
  cloné : une version qui désigne un tag (`refs/tags/<version>`) est lue comme un tag, même si une
  branche porte le même nom ; sinon, une version qui n'est pas un commit complet est une erreur.
  Le clone reste alors en place, comme le clone d'une version introuvable en 0.5.4.0.
- **P-V2.** Emplacement distant : le clone va sous `depots/<shelf>/<prefix>/<version>`, comme pour
  un scion ordinaire. Deux clés de même `prefix` et de même version partagent donc le clone. Il est
  créé par `git clone --filter=blob:none --no-checkout`, puis `git checkout --detach <version>`.
  `--single-branch` est sans effet pour une clé projetée. Un clone partagé entre une clé projetée et
  un scion ordinaire (même `shelf`, `prefix` et version) est une erreur de résolution.
- **P-V3.** Emplacement local : le chemin doit être un dépôt git, utilisé tel quel, jamais cloné ni
  déplacé.
- **P-V4.** Tag : `HEAD` doit être le commit du tag ; un tag déplacé dans `origin` arrête
  `graft-update`, `seed-update` et `seed-add`, comme en 0.5.4.0. Commit : `HEAD` doit être ce
  commit ; s'il est absent du clone, `git fetch origin` (toutes les références) est tenté, puis
  c'est une erreur. Aucun fetch par empreinte : il dépend de la configuration du serveur.
- **P-V5.** Changer la version d'une clé projetée crée un nouveau clone (la version entre dans le
  chemin) ; l'ancien reste, `graft-remove --purge` ne le touche pas.
- **P-V6.** La règle « un scion déjà greffé dans une version plus récente est conservé » ne
  s'applique pas à une clé projetée : un commit ne se compare pas, et la projection suit son
  `.scion/`. La version déclarée remplace toujours la version greffée.
- **P-E1.** Avant toute greffe d'une clé projetée, le clone doit être à son commit épinglé
  (`HEAD`) et sans modification de fichier suivi (`git status --porcelain --untracked-files=no`
  vide). Sinon la greffe s'arrête (code 1, trunk rétabli) et nomme le clone et les fichiers. Les
  fichiers non suivis ne bloquent rien et ne sont jamais projetés (P-M4). Le contrôle a lieu avant
  le dégreffage : un refus laisse le trunk tel qu'il était.

### A.9 Scion porteur

- **P-P1.** Un scion ordinaire dont le répertoire `scion/.scion/` contient un `.scion.projections`
  est un **porteur**. Ce `.scion/` a le format d'une graine (`.scion.sources.list`,
  `.scion.ramifications`, `.scion.projections`). Il n'est jamais greffé (`.scion/` est sauté, comme
  en 0.5.4.0).
- **P-P2.** Un porteur ne déclare **que des clés projetées** : une clé de ses sources ou de ses
  ramifications sans ligne d'inclusion dans son `.scion.projections` est une erreur. Il n'y a donc
  qu'un niveau : un dépôt tiers n'a pas de `scion/`, donc pas de porteur.
- **P-P3.** Résolution d'une graine : ses scions d'abord, puis le `.scion/` de chaque scion ordinaire
  résolu qui est porteur, dans l'ordre des ramifications de la graine. Les clés projetées d'un porteur
  entrent dans `.scion.grafted.list` avec, en 5ᵉ colonne, la graine (comme tout scion) et, en 6ᵉ, le
  `.scion/` du porteur. La greffe lit les lignes de projection dans le `.scion/` de la 6ᵉ colonne,
  ou de la 5ᵉ si la 6ᵉ est absente.
- **P-P4.** Une même clé projetée déclarée dans deux `.scion/` (graine et porteur, ou deux
  porteurs) : erreur, sauf si ses lignes de sources, de ramifications et de projection sont
  identiques dans les deux. Les lignes sont comparées après normalisation des blancs, et les
  projections comme un ensemble. La clé n'est alors greffée qu'une fois ; sa 6ᵉ colonne est le
  premier `.scion/` dans l'ordre P-P3 (absente si c'est la graine).
- **P-P5.** La projection avance avec le porteur. Quand `graft-update` ou `seed-update` avance le
  clone d'un porteur, son `.scion/` est relu après l'avance. Une version nouvelle d'une clé projetée
  y est clonée (P-V5). Les clones projetés déjà connus sont contrôlés avec ceux de la graine, avant
  toute avance (P-V4) ; un clone déjà présent pour une version nouvelle est contrôlé à la greffe
  (P-E1, trunk rétabli).
- **P-P6.** `graft-remove <porteur>` retire aussi du trunk et de la liste greffée les clés projetées
  qu'il porte, et le dit. `--purge` s'applique au seul clone du porteur.
- **P-P7.** Une clé projetée que son porteur ne déclare plus (après une avance ou une édition) est
  retirée de la liste greffée à la résolution suivante de la graine, avec un message ; la regreffe
  retire ses liens. Son clone reste. Ce n'est pas le cas d'une clé retirée d'une graine, qui reste
  greffée comme en 0.5.4.0.

### A.10 Greffe, propriété et retrait

- **P-G1.** Les liens d'une clé projetée sont relatifs, comme les autres. Ils pointent dans le clone
  tiers, vers le fichier source. Leurs répertoires parents sont de vrais répertoires du trunk,
  partageables avec les autres scions.
- **P-G2.** Conflits entre scions : inchangés. Un chemin du trunk fourni par deux scions,
  projetés ou non, est un conflit. Tous les conflits sont collectés, et la greffe est annulée sans
  rien laisser. Il n'y a aucune superposition : pour remplacer un fichier tiers par une version
  locale, on l'exclut (`!motif`) et un autre scion le fournit.
- **P-G3.** Propriété : un lien appartient à la clé dont le clone (racine, pour une clé projetée)
  préfixe sa cible. Un répertoire du trunk appartient à une clé projetée s'il est l'ancêtre d'un
  de ses chemins du trunk. Cela vaut pour le message de conflit, `graft --scion`, `graft-remove` et
  l'élagage des répertoires vides. Quand plusieurs clés projetées partagent un clone (P-V2), un lien
  appartient à celle dont la table contient son chemin du trunk ; un lien du clone qui n'est dans
  aucune table est retiré par la regreffe ou le retrait de toute clé de ce clone.
- **P-G4.** Le filtre des fichiers ignorés (0.5.2.0) ne s'applique pas à une clé projetée : la liste
  git l'a déjà exclu.
- **P-G5.** `graft --scion <clé projetée>` relit ses lignes de projection et regreffe la clé seule ;
  le reste du trunk est conservé (règles de 0.5.1.0).

### A.11 Commandes touchées

| Commande | Effet de la projection |
| --- | --- |
| `seed-add`, `seed-clone` | clonent aussi les clés projetées de la graine et des porteurs (P-P3, P-V2) |
| `seed-update`, `graft-update` | contrôlent et avancent comme en 0.5.4.0, puis relisent les porteurs (P-P5, P-P7) ; contrôles P-V4 |
| `graft` (complet, `--scion`) | résolution P-R*, casse P-K2, état du clone P-E1, conflits P-G2 ; trunk rétabli en cas d'échec |
| `graft-remove [--purge]` | P-G3, P-P6 |
| `ungraft`, `graft-clean` | inchangés |
| `seed-scion-add`, `seed-scion-remove` | inchangés ; aucune commande n'écrit `.scion.projections` (édition à la main) |
| `git --key` | admis pour une clé projetée |
| `rootstock-information` | `scions grafted: N` compte aussi les clés projetées ; une ligne `scions projected: k` s'ajoute seulement si k > 0 (P-C1) |

### A.12 Messages et codes de retour

- Code 0 : succès. Code 1 (`ScionError`) : toute erreur de cette spécification. Code 2 : échec
  d'une commande git (`GitError`), ou usage incorrect de la ligne de commande.
- Chaque message d'erreur nomme le fichier et le numéro de ligne en cause, la clé et, selon le cas,
  le motif, la destination, le chemin du trunk ou le clone. Il se termine, quand une seule action
  corrige l'erreur, par cette action (par exemple `git -C <clone> checkout --detach <version>`).
- `-v` liste, pour chaque clé projetée, le nombre de fichiers par ligne et les fichiers exclus.

## B. Miroir de conservation

### B.1 Déclaration : `.scion.mirrors`

```
<url du miroir>   <url de l'amont>
```

- **M-D1.** Le fichier se trouve dans un `.scion/` : celui d'une graine ou d'un porteur. Il sert
  au `.scion/` qui déclare une source pointant vers ce miroir.
- **M-D2.** Le dépôt d'une clé se déclare par l'URL de son **miroir** dans `.scion.sources.list`.
  La greffe ne lit jamais `.scion.mirrors` : la graine ne dépend que du miroir.
- **M-D3.** Une ligne non vide qui n'a pas exactement 2 champs, ou dont un champ n'est pas une URL
  distante, est une erreur (fichier, numéro de ligne).
- **M-D4.** Un même miroir associé à deux amonts différents, dans un ou plusieurs `.scion/`, est
  une erreur.
- **M-D5.** Quand le clonage ou le contrôle d'une version échoue sur une URL déclarée comme miroir,
  le message suggère `scion mirror-sync`.

### B.2 Commande `mirror-sync`

```
scion mirror-sync [rootstock] [--seed <graine>] [--dry-run] [<url du miroir>…]
```

- **M-C1.** Miroirs traités : ceux des `.scion.mirrors` de la graine (`--seed`) ou de toutes les
  graines de la liste greffée, et des porteurs greffés. Si des URL sont données, seules celles-là
  sont traitées. Une URL inconnue est une erreur, signalée avant tout traitement.
- **M-C2.** Dépôt de travail : `depots/.mirrors/<hôte>/<chemin>` (tiré de l'URL du miroir), créé par
  `git clone --mirror <miroir>`, puis rafraîchi par `git fetch`. Les références de l'amont sont
  rapatriées dans un espace séparé (`refs/amont/heads/*`, `refs/amont/tags/*`), jamais sur celles du
  miroir.
- **M-C3.** Seules les branches (`refs/heads/*`) et les tags (`refs/tags/*`) sont traités.
- **M-C4.** Envoi : `git push <miroir>` de références nommées une à une, jamais `--force`,
  `--mirror`, `--prune`, ni suppression. scion n'emploie que l'authentification git de l'utilisateur.
- **M-C5.** scion ne crée jamais de dépôt distant. Un miroir inaccessible est signalé ; les autres
  sont traités.
- **M-C6.** `--dry-run` : tout est calculé et rapporté, rien n'est envoyé.

### B.3 Règles par référence

| Cas (amont comparé au miroir) | Action | Message |
| --- | --- | --- |
| **M-R1** branche absente du miroir | envoyée | info |
| **M-R2** branche du miroir ancêtre de celle de l'amont | envoyée (avance rapide) | info |
| **M-R3** branche identique | rien | `-v` |
| **M-R4** branche réécrite (le miroir n'est pas ancêtre) | **non envoyée** | signalement |
| **M-R5** branche supprimée dans l'amont | conservée dans le miroir | signalement |
| **M-R6** tag absent du miroir | envoyé | info |
| **M-R7** tag identique (même objet) | rien | `-v` |
| **M-R8** tag déplacé (objet différent) | **non propagé** | signalement (deux commits) |
| **M-R9** tag supprimé dans l'amont | conservé dans le miroir | signalement |

- **M-K1.** Code 0 : aucun signalement. Code 1 : au moins un signalement (M-R4, M-R5, M-R8, M-R9,
  miroir inaccessible) ou une erreur de déclaration. Code 2 : échec git inattendu, ou usage
  incorrect. Le bilan final compte les références envoyées et les signalements par miroir.
- **M-K2.** Rien n'est jamais supprimé ni réécrit dans un miroir.

## C. Hors périmètre

- Fichiers dérivés d'un fichier tiers et modifiés (correctifs) : ils restent des fichiers d'un scion
  ordinaire, et la projection les exclut (P-G2). Le format ne dit pas de quel fichier tiers ils
  dérivent.
- Commandes d'édition de `.scion.projections` et `.scion.mirrors`.
- `sparse-checkout` du clone tiers.
- Création, visibilité ou suppression des dépôts miroirs.
- Branche par défaut (`HEAD`) du miroir ; références autres que branches et tags.
