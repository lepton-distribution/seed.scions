"""Turning seeds into a grafted list, and the grafted list into a trunk.

The trunk is disposable: every directory in it is a real directory and every
leaf is a relative symlink into ``depots/``. Nothing is ever written inside a
clone, and a moved rootstock keeps working without re-grafting.
"""

from __future__ import annotations

import fnmatch
import logging
import os
import shutil
from collections import OrderedDict
from pathlib import Path
from urllib.parse import urlparse

from . import gitops
from .errors import GitError, ScionError
from .model import (
    GRAFTED_LIST,
    PROJECTIONS,
    RAMIFICATIONS,
    SOURCES_LIST,
    GraftedEntry,
    compare,
    read_grafted,
    read_ramifications,
    read_sources,
    select_source,
    write_grafted,
)
from .projection import (
    Listing,
    Resolution,
    case_collisions,
    has_projections,
    read_dot,
    read_projections,
    resolve as resolve_projection,
)
from .rootstock import HIDDEN_DIR, STEM_DIR, Rootstock, relative_link

log = logging.getLogger(__name__)


def is_remote(location: str) -> bool:
    return bool(urlparse(location).netloc)


# --------------------------------------------------------------------------
# seeds -> grafted list
# --------------------------------------------------------------------------
#: one scion a ``.scion/`` brings: (entry, url or "", clone directory, projected)
Wanted = tuple[GraftedEntry, str, str, bool]


def sync(rootstock: Rootstock, seed_dot_scion: Path, single_branch: bool = False) -> None:
    """Resolve one seed into the grafted list, cloning what is missing.

    Clones are grouped by destination, so a seed declaring sixteen scions cut
    out of the same repository clones it once. An existing clone is left as it
    is: :func:`update_sources` is what moves clones. The scions of the seed
    come first, then the projected scions of each carrier among them, read
    once the carriers are cloned.
    """
    dot = Path(seed_dot_scion).resolve()
    entries = read_grafted(rootstock.grafted_list)
    wanted = _wanted(rootstock, dot, entries)
    _fetch(wanted, single_branch)
    carried, carried_keys = _carried(rootstock, dot, entries)
    _fetch(carried, single_branch)
    _forget_uncarried(rootstock, dot, entries, carried_keys)
    for entry, _, clone_dir, projected in wanted + carried:
        if projected:
            _check_local_repository(entry, Path(clone_dir))
            continue
        stem = rootstock.resolve(entry.local_path) / STEM_DIR
        if not stem.is_dir():
            raise ScionError(
                f"scion « {entry.ref.key} » : {stem} est absent. Vérifiez la colonne "
                f"« chemin dans le dépôt » de {SOURCES_LIST}"
            )
    _check_shared_clones(rootstock, entries)
    rootstock.grafted_list.parent.mkdir(parents=True, exist_ok=True)
    write_grafted(rootstock.grafted_list, entries.values())


def _projected_in(dot: Path, carrier: bool) -> set[str]:
    """The projected keys a ``.scion/`` declares; the file is checked on the way."""
    return read_dot(dot, carrier).projected if has_projections(dot) else set()


def _wanted(rootstock: Rootstock, dot: Path, entries, seed: Path | None = None,
            only: set[str] | None = None) -> list[Wanted]:
    """The scions ``dot`` brings, as :data:`Wanted`.

    ``dot`` is a seed's ``.scion/``, or -- with ``seed`` -- a carrier's, whose
    scions then belong to ``seed``; ``only`` restricts them to some keys.
    ``entries`` -- the grafted list -- is updated in place; a scion grafted in
    a more recent version is kept, and left out of the result, unless it is
    projected: a projected scion follows its declaration.
    """
    sources = read_sources(dot / SOURCES_LIST)
    projected = _projected_in(dot, carrier=seed is not None)
    wanted: list[Wanted] = []
    errors: list[str] = []
    for ref in read_ramifications(dot / RAMIFICATIONS):
        if only is not None and ref.key not in only:
            continue
        source = select_source(sources, ref)
        is_projected = ref.key in projected
        if is_projected:
            fault = _projected_declaration_fault(ref.version, source)
            if fault:
                errors.append(f"{dot} : clé projetée « {ref.key} » : {fault}")
                continue
        if is_remote(source.location):
            clone_dir = (
                rootstock.depots / source.ref.shelf / source.ref.prefix / source.ref.version
            )
        else:
            clone_dir = rootstock.resolve(source.location)
        local = clone_dir / source.subpath if source.subpath else clone_dir
        entry = GraftedEntry(source.ref, rootstock.store(local),
                             rootstock.store(seed if seed is not None else dot),
                             rootstock.store(dot) if seed is not None else "")

        previous = entries.get(entry.ref.key)
        if (not is_projected and previous is not None
                and compare(previous.ref.version, entry.ref.version) > 0):
            log.info(
                "scion %s : la version greffée %s est plus récente que %s, conservée",
                entry.ref.key, previous.ref.version, entry.ref.version,
            )
            continue
        entries[entry.ref.key] = entry
        wanted.append((entry, source.location if is_remote(source.location) else "",
                       str(clone_dir), is_projected))
    if errors:
        raise ScionError("\n".join(errors))
    return wanted


def _projected_declaration_fault(declared: str, source) -> str | None:
    if source.subpath:
        return (f"la colonne « chemin dans le dépôt » ({source.subpath}) est refusée : "
                f"une clé projetée est greffée par {PROJECTIONS}")
    for version in (declared, source.ref.version):
        if version in ("*", "?"):
            return (f"version « {version} » refusée : une clé projetée est épinglée par un tag "
                    "ou un commit complet")
    return None


def _carrier_dot(rootstock: Rootstock, entry: GraftedEntry) -> Path:
    return rootstock.resolve(entry.local_path) / STEM_DIR / HIDDEN_DIR


def _carried(rootstock: Rootstock, dot: Path, entries) -> tuple[list[Wanted], set[str]]:
    """The projected scions the carriers of the seed ``dot`` bring.

    Carriers are the seed's scions -- in the order of its ramifications, then
    those of its scions still grafted -- whose ``scion/.scion/`` holds a
    projection file. A key declared twice must be declared identically; the
    first declaration wins. Carriers not cloned yet are skipped.
    """
    stored = rootstock.store(dot)
    declared: dict[str, object] = {}
    if has_projections(dot):
        seed = read_dot(dot, carrier=False)
        declared.update({key: seed for key in seed.projected})
    order = [ref.key for ref in read_ramifications(dot / RAMIFICATIONS)]
    order += [key for key, entry in entries.items()
              if entry.seed_dot_scion == stored and not entry.carrier and key not in order]
    wanted: list[Wanted] = []
    keys: set[str] = set()
    errors: list[str] = []
    for key in order:
        entry = entries.get(key)
        if entry is None or entry.carrier or key in declared:
            continue
        carrier = _carrier_dot(rootstock, entry)
        if not has_projections(carrier):
            continue
        parsed = read_dot(carrier, carrier=True)
        take: set[str] = set()
        for projected in sorted(parsed.projected):
            first = declared.get(projected)
            if first is None:
                declared[projected] = parsed
                take.add(projected)
            elif first.signature(projected) != parsed.signature(projected):
                errors.append(f"clé projetée « {projected} » déclarée différemment dans "
                              f"{first.dot} et {carrier} ; une seule déclaration, ou deux "
                              "identiques")
        keys |= take
        if take:
            wanted += _wanted(rootstock, carrier, entries, seed=dot, only=take)
    if errors:
        raise ScionError("\n".join(errors))
    return wanted, keys


def _forget_uncarried(rootstock: Rootstock, dot: Path, entries, carried: set[str]) -> None:
    """Drop the projected scions of the seed ``dot`` that no carrier declares any more."""
    stored = rootstock.store(dot)
    for key in [key for key, entry in entries.items()
                if entry.seed_dot_scion == stored and entry.carrier and key not in carried]:
        log.info("clé projetée %s retirée de la liste greffée : %s ne la déclare plus",
                 key, entries[key].carrier)
        del entries[key]


def _check_local_repository(entry: GraftedEntry, clone: Path) -> None:
    top = gitops.toplevel(clone) if clone.is_dir() else None
    if top is None or top.resolve() != clone.resolve():
        raise ScionError(f"clé projetée « {entry.ref.key} » : {clone} n'est pas la racine "
                         "d'un dépôt git")


def projected_keys(rootstock: Rootstock, entries) -> set[str]:
    """The keys of the grafted list that are projected."""
    cache: dict[str, set[str]] = {}
    found: set[str] = set()
    for key, entry in entries.items():
        if entry.carrier:
            found.add(key)
            continue
        if not entry.seed_dot_scion:
            continue
        if entry.seed_dot_scion not in cache:
            seed = rootstock.resolve(entry.seed_dot_scion)
            cache[entry.seed_dot_scion] = (
                {line.key for line in read_projections(seed / PROJECTIONS) if not line.exclude}
                if has_projections(seed) else set()
            )
        if key in cache[entry.seed_dot_scion]:
            found.add(key)
    return found


def _check_shared_clones(rootstock: Rootstock, entries) -> None:
    """A clone is never shared between a projected scion and an ordinary one."""
    projected = projected_keys(rootstock, entries)
    if not projected:
        return
    roots = {key: rootstock.resolve(entries[key].local_path).resolve() for key in projected}
    errors = []
    for key, entry in entries.items():
        if key in projected:
            continue
        local = rootstock.resolve(entry.local_path).resolve()
        for other, root in roots.items():
            if _inside(local, root):
                errors.append(f"clone {root} partagé entre la clé projetée « {other} » et le "
                              f"scion « {key} » ; changez la version ou le shelf de l'une")
    if errors:
        raise ScionError("\n".join(errors))


def _remote_clones(wanted) -> OrderedDict[str, tuple[str, str, bool]]:
    """Each distinct clone of a remote scion: URL, declared version, projected."""
    seen: OrderedDict[str, tuple[str, str, bool]] = OrderedDict()
    for entry, url, clone_dir, projected in wanted:
        if url:
            seen.setdefault(clone_dir, (url, entry.ref.version, projected))
    return seen


def _fetch(wanted, single_branch: bool) -> None:
    """Clone each missing repository exactly once."""
    for clone_dir, (url, version, projected) in _remote_clones(wanted).items():
        destination = Path(clone_dir)
        if (destination / ".git").exists():
            continue
        if not projected:
            gitops.clone(url, destination, version, single_branch)
            continue
        gitops.clone_partial(url, destination)
        pinned, fault = _pinned(destination, version)
        if fault:
            raise ScionError(f"{destination} : {fault} (clone laissé en place)")
        gitops.checkout_detached(destination, pinned)


def _pinned(clone: Path, version: str) -> tuple[str | None, str | None]:
    """The commit a projected scion's version designates, or why it has none."""
    if gitops.is_full_sha(version):
        if gitops.has_commit(clone, version):
            return version.lower(), None
        return None, f"commit « {version} » absent du dépôt"
    tagged = gitops.tag_commit(clone, version)
    if tagged is not None:
        return tagged, None
    if gitops.is_branch(clone, version):
        return None, (f"« {version} » est une branche : une clé projetée est épinglée par un "
                      "tag ou un commit complet (40 caractères)")
    return None, (f"version « {version} » introuvable : ni tag, ni commit complet "
                  "(40 caractères)")


# --------------------------------------------------------------------------
# clones at their declared version
# --------------------------------------------------------------------------
def update_sources(rootstock: Rootstock, seed_dots, movable_seeds=None) -> None:
    """Bring the seeds, then their clones, to their declared versions.

    Only by fast-forward from their upstreams. Every check comes first: a seed
    or a clone that cannot be moved stops the command before anything has
    changed. The clones are checked against the seeds as they are, then again,
    for the clones they did not name yet, once the seeds have moved.
    ``movable_seeds`` -- by default every seed -- are the seeds allowed to move.
    """
    seed_dots = [Path(dot) for dot in seed_dots]
    behind_seeds = seed_updates(rootstock, seed_dots if movable_seeds is None else movable_seeds)
    checked: set[str] = set()
    behind = clone_updates(rootstock, seed_dots, checked)
    advance_seeds(behind_seeds)
    if behind_seeds:
        behind += clone_updates(rootstock, seed_dots, checked)
    advance_clones(behind)


def clone_updates(rootstock: Rootstock, seed_dots, checked: set[str] | None = None) -> list[Path]:
    """The existing clones to fast-forward; stop on any that cannot be.

    A clone of a branch must have that branch checked out, an upstream, and no
    divergence from it; behind its upstream, it must have no changes to
    tracked files. A clone of a tag must have that tag checked out, and the
    tag must not have moved in ``origin``. Every clone is checked before the
    error is raised, so that it names them all. Clones already in ``checked``
    are skipped; those checked here are added to it.
    """
    checked = set() if checked is None else checked
    faults: list[str] = []
    behind: list[Path] = []
    for dot in seed_dots:
        entries = read_grafted(rootstock.grafted_list)
        wanted = _wanted(rootstock, Path(dot).resolve(), entries)
        wanted += _carried(rootstock, Path(dot).resolve(), entries)[0]
        for clone_dir, (_, version, projected) in _remote_clones(wanted).items():
            if clone_dir in checked:
                continue
            checked.add(clone_dir)
            destination = Path(clone_dir).resolve()
            if not (destination / ".git").exists():
                continue
            if projected:
                fault, late = _check_projected_clone(destination, version), False
            else:
                fault, late = _check_clone(destination, version)
            if fault:
                faults.append(fault)
            elif late:
                behind.append(destination)
    if faults:
        raise ScionError(
            f"{len(faults)} clone(s) à remettre à leur version déclarée avant la mise à jour "
            "(trunk et clones inchangés) :\n" + "\n".join(f"  {fault}" for fault in faults)
        )
    return behind


def _check_clone(clone: Path, version: str) -> tuple[str | None, bool]:
    """``(fault, behind)`` for one clone and its declared version."""
    branch = gitops.current_branch(clone)
    where = f"branche « {branch} »" if branch else f"HEAD détaché sur {gitops.head(clone)}"
    if gitops.is_branch(clone, version):
        if branch != version:
            return (f"{clone} : {where}, version déclarée « {version} » ; "
                    f"git -C {clone} switch {version}"), False
        upstream = gitops.upstream(clone)
        if upstream is None:
            return f"{clone} : branche « {version} » sans amont", False
        gitops.fetch(clone)
        ahead, late = gitops.ahead_behind(clone)
        if ahead and late:
            return (f"{clone} : branche « {version} » divergée de {upstream} ({ahead} commit(s) "
                    f"locaux, {late} distant(s)) ; réconciliez-la"), False
        if late and gitops.tracked_changes(clone):
            return (f"{clone} : modifications non commitées et {late} commit(s) de retard sur "
                    f"{upstream} ; commitez-les ou annulez-les"), False
        if ahead:
            log.info("clone %s : %d commit(s) non publié(s), laissé tel quel", clone, ahead)
        return None, bool(late)
    tagged = gitops.tag_commit(clone, version)
    if tagged is None:
        return f"{clone} : version déclarée « {version} » introuvable dans le clone", False
    if gitops.commit(clone) != tagged:
        return (f"{clone} : {where}, version déclarée : tag « {version} » ; "
                f"git -C {clone} switch --detach {version}"), False
    published = gitops.remote_tag_commit(clone, version)
    if published is None:
        log.info("clone %s : tag « %s » absent de l'amont, laissé tel quel", clone, version)
    elif published != tagged:
        return (f"{clone} : tag « {version} » déplacé dans l'amont ({tagged[:7]} -> "
                f"{published[:7]}) ; vérifiez la version avant de reprendre le tag"), False
    return None, False


def _check_projected_clone(clone: Path, version: str) -> str | None:
    """The fault of a projected scion's clone, ``None`` if it is at its version.

    It never moves: its version is a tag, which must not have moved in
    ``origin``, or a commit, fetched from ``origin`` when the clone lacks it.
    """
    if gitops.is_full_sha(version) and not gitops.has_commit(clone, version):
        gitops.fetch_origin(clone)
    pinned, fault = _pinned(clone, version)
    if fault:
        return f"{clone} : {fault}"
    if gitops.commit(clone) != pinned:
        return (f"{clone} : HEAD sur {gitops.head(clone)}, version déclarée « {version} » ; "
                f"git -C {clone} checkout --detach {version}")
    if not gitops.is_full_sha(version):
        published = gitops.remote_tag_commit(clone, version)
        if published is not None and published != pinned:
            return (f"{clone} : tag « {version} » déplacé dans l'amont ({pinned[:7]} -> "
                    f"{published[:7]}) ; vérifiez la version avant de reprendre le tag")
        if published is None:
            log.info("clone %s : tag « %s » absent de l'amont, laissé tel quel", clone, version)
    return None


def advance_clones(clones: list[Path]) -> None:
    """Fast-forward the clones :func:`clone_updates` returned."""
    for clone in clones:
        before = gitops.head(clone)
        gitops.fast_forward(clone)
        log.info("clone %s avancé : %s -> %s", clone, before, gitops.head(clone))


def seed_updates(rootstock: Rootstock, seed_dots) -> list[Path]:
    """The seed repositories to fast-forward; stop on any that cannot be.

    A seed moves with its upstream, by fast-forward only. One with changes to
    tracked files, or one that diverged, is an error; nothing has been changed
    yet when it is raised. A seed outside git, without an upstream, or in the
    repository that holds the rootstock itself is left as it is, and so is one
    that is only ahead of its upstream.
    """
    behind: list[Path] = []
    seen: set[Path] = set()
    for dot in seed_dots:
        top = gitops.toplevel(Path(dot))
        if top is None:
            log.debug("graine %s : hors git, laissée telle quelle", dot)
            continue
        top = top.resolve()
        if top in seen:
            continue
        seen.add(top)
        if _inside(rootstock.path.resolve(), top):
            log.debug("graine %s : dans le dépôt du rootstock, laissée telle quelle", top)
            continue
        upstream = gitops.upstream(top)
        if upstream is None:
            log.debug("graine %s : sans amont, laissée telle quelle", top)
            continue
        if gitops.tracked_changes(top):
            raise ScionError(
                f"graine {top} : modifications non commitées ; commitez-les ou "
                "annulez-les avant la mise à jour (rien n'a été modifié)"
            )
        gitops.fetch(top)
        ahead, late = gitops.ahead_behind(top)
        if ahead and late:
            raise ScionError(
                f"graine {top} : branche divergée de {upstream} ({ahead} commit(s) "
                f"locaux, {late} distant(s)) ; réconciliez-la avant la mise à jour "
                "(rien n'a été modifié)"
            )
        if ahead:
            log.info("graine %s : %d commit(s) non publié(s), laissée telle quelle", top, ahead)
        elif late:
            behind.append(top)
    return behind


def advance_seeds(seed_repositories: list[Path]) -> None:
    """Fast-forward the repositories :func:`seed_updates` returned."""
    for top in seed_repositories:
        before = gitops.head(top)
        gitops.fast_forward(top)
        log.info("graine %s avancée : %s -> %s", top, before, gitops.head(top))


def seeds(rootstock: Rootstock) -> list[str]:
    """The distinct seeds recorded in the grafted list, in insertion order."""
    found: list[str] = []
    for entry in read_grafted(rootstock.grafted_list).values():
        if entry.seed_dot_scion and entry.seed_dot_scion not in found:
            found.append(entry.seed_dot_scion)
    return found


def clean(rootstock: Rootstock) -> None:
    """Forget every grafted scion; the clones in depots/ are left alone.

    The file is emptied rather than removed: it is what marks the trunk, and
    deleting it would make the rootstock undiscoverable.
    """
    rootstock.grafted_list.parent.mkdir(parents=True, exist_ok=True)
    rootstock.grafted_list.write_text("")


# --------------------------------------------------------------------------
# grafted list -> trunk
# --------------------------------------------------------------------------
def _walk(base: Path, ignored: frozenset[Path] | set[Path] = frozenset()):
    """Yield ``("dir"|"leaf", path relative to base)`` for a scion.

    ``.scion/`` is skipped at every level, and a symlink committed in the
    repository is a leaf even when it points at a directory: it is copied as a
    link, never followed. A path in ``ignored`` is skipped, and so is
    everything below it.
    """
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        here = Path(dirpath)
        relative = here.relative_to(base)
        linked = [name for name in dirnames if (here / name).is_symlink()]
        dirnames[:] = sorted(
            name for name in dirnames
            if name != HIDDEN_DIR and name not in linked and relative / name not in ignored
        )
        yield "dir", relative
        for name in sorted(filenames) + sorted(linked):
            if relative / name not in ignored:
                yield "leaf", relative / name


def _ignored(rootstock: Rootstock, entry: GraftedEntry, stem: Path) -> set[Path]:
    """What git ignores under ``stem``, relative to it: never grafted.

    A scion outside git follows the same rules, those of its own ``.gitignore``
    files and of the global configuration. A scion whose work tree holds the
    rootstock itself ignores nothing, since those rules belong to the
    rootstock's own repository, not to the scion.
    """
    top = gitops.toplevel(stem)
    if top is None:
        names = gitops.ignored_outside(stem.parent, stem)
    elif _inside(rootstock.path.resolve(), top.resolve()):
        return set()
    else:
        names = gitops.ignored(stem)
    ignored = {Path(name.rstrip("/")) for name in names}
    for relative in sorted(ignored):
        log.debug("exclu (ignoré par git) : %s %s", entry.ref.key, relative)
    return ignored


def _mkdir(path: Path, created: list[Path]) -> None:
    """Create ``path``, remembering the directories that did not exist."""
    if path.is_dir():
        return
    missing = []
    walker = path
    while not walker.exists():
        missing.append(walker)
        walker = walker.parent
    path.mkdir(parents=True)
    created.extend(reversed(missing))


def _rollback(links: list[Path], directories: list[Path]) -> None:
    for link in reversed(links):
        link.unlink(missing_ok=True)
    for directory in reversed(directories):
        try:
            directory.rmdir()
        except OSError:
            pass


def graft(rootstock: Rootstock, plans: dict[str, Resolution] | None = None) -> int:
    """Graft every scion of the grafted list onto the trunk.

    Conflicts are all collected before anything is reported, and a conflicting
    graft leaves nothing behind: what this call created is undone. ``plans``
    -- the projected scions, resolved and checked -- are computed when absent.
    """
    entries = read_grafted(rootstock.grafted_list)
    if not entries:
        raise ScionError(
            f"{rootstock.grafted_list} est vide : ajoutez un seed avec « scion seed-add »"
        )
    if plans is None:
        plans = _projections(rootstock, entries)[1]
    rootstock.trunk.mkdir(parents=True, exist_ok=True)
    links = _graft_entries(rootstock, list(entries.values()), entries, set(plans), plans)
    log.info("greffe : %d feuilles liées dans %s", len(links), rootstock.trunk)
    return len(links)


def _stem(rootstock: Rootstock, entry: GraftedEntry) -> Path:
    return rootstock.resolve(entry.local_path) / STEM_DIR


def _within(relative: Path, base: Path) -> bool:
    return relative.parts[: len(base.parts)] == base.parts


# --------------------------------------------------------------------------
# projected scions: resolution, state of their clones
# --------------------------------------------------------------------------
def _projections(rootstock: Rootstock, entries, strict: set[str] | None = None
                 ) -> tuple[set[str], dict[str, Resolution]]:
    """The projected keys of the grafted list, and the files of each.

    For the keys in ``strict`` -- all of them by default -- the clone must be
    at its pinned commit without changes to tracked files, and every error is
    collected and raised. The other keys are resolved as best as possible,
    for ownership only; one that cannot be is left out of the tables.
    """
    try:
        projected = projected_keys(rootstock, entries)
    except ScionError:
        if strict is not None and not strict:
            return set(), {}
        raise
    strict = projected if strict is None else strict & projected
    cache: dict[str, list] = {}
    tables: dict[str, Resolution] = {}
    errors: list[str] = []
    for key in (key for key in entries if key in projected):
        entry = entries[key]
        root = rootstock.resolve(entry.local_path)
        try:
            if entry.declared_in not in cache:
                dot = rootstock.resolve(entry.declared_in)
                cache[entry.declared_in] = read_projections(dot / PROJECTIONS)
            if key in strict:
                commit = _projected_state(root, entry)
            else:
                commit = _pinned(root, entry.ref.version)[0] or "HEAD"
            listing = Listing.from_tree(gitops.ls_tree(root, commit))
            tables[key] = resolve_projection(key, cache[entry.declared_in], listing)
        except ScionError as exc:
            if key not in strict:
                log.debug("clé projetée %s non résolue : %s", key, exc)
            elif isinstance(exc, GitError):
                raise
            else:
                errors.append(str(exc))
    if errors:
        raise ScionError("\n".join(errors))
    return projected, tables


def _projected_state(root: Path, entry: GraftedEntry) -> str:
    """The pinned commit of a projected scion, its clone checked first."""
    key, version = entry.ref.key, entry.ref.version
    if not (root / ".git").exists():
        raise ScionError(f"clé projetée « {key} » : {root} n'est pas un clone git ; "
                         "scion seed-clone")
    pinned, fault = _pinned(root, version)
    if fault:
        raise ScionError(f"clé projetée « {key} » : {root} : {fault}")
    if gitops.commit(root) != pinned:
        raise ScionError(
            f"clé projetée « {key} » : {root} : HEAD sur {gitops.head(root)}, version "
            f"déclarée « {version} » ; git -C {root} checkout --detach {version}"
        )
    changed = gitops.tracked_changes(root)
    if changed:
        files = ", ".join(line[3:] for line in changed.splitlines())
        raise ScionError(
            f"clé projetée « {key} » : {root} : fichiers suivis modifiés ({files}) ; "
            f"annulez-les avant de greffer (git -C {root} stash)"
        )
    return pinned


def _items(rootstock: Rootstock, entry: GraftedEntry, plan: Resolution | None):
    """``([(kind, relative, source)], ignored)`` of one scion, in grafting order."""
    if plan is not None:
        root = rootstock.resolve(entry.local_path)
        items: list[tuple[str, Path, Path | None]] = [("dir", Path("."), None)]
        seen: set[str] = set()
        for path in sorted(plan.table):
            parts = path.split("/")
            for depth in range(1, len(parts)):
                directory = "/".join(parts[:depth])
                if directory not in seen:
                    seen.add(directory)
                    items.append(("dir", Path(directory), None))
            items.append(("leaf", Path(path), root / plan.table[path]))
        return items, 0
    stem = _stem(rootstock, entry)
    if not stem.is_dir():
        raise ScionError(f"scion « {entry.ref.key} » : {stem} est absent")
    ignored = _ignored(rootstock, entry, stem)
    return [(kind, relative, stem / relative) for kind, relative in _walk(stem, ignored)], \
        len(ignored)


def _check_case(rootstock: Rootstock, planned, plans, tables, partial: bool) -> None:
    """Stop on trunk paths that differ only by case, one at least projected."""
    paths: dict[str, tuple[str, bool]] = {}
    chosen = {entry.ref.key for entry, _, _ in planned}
    for entry, items, _ in planned:
        for _, relative, _ in items:
            if str(relative) != ".":
                paths.setdefault(str(relative), (entry.ref.key, entry.ref.key in plans))
    if partial:
        trunk = rootstock.trunk
        others = [(key, table) for key, table in tables.items() if key not in chosen]
        for dirpath, dirnames, filenames in os.walk(trunk, followlinks=False):
            for name in dirnames + filenames:
                relative = str((Path(dirpath) / name).relative_to(trunk))
                if relative == GRAFTED_LIST or relative in paths:
                    continue
                owner = next((key for key, table in others
                              if relative in table.table or relative in table.dirs), None)
                paths[relative] = (owner or "trunk", owner is not None)
    collisions = case_collisions(paths)
    if collisions:
        raise ScionError("\n".join(
            [f"{len(collisions)} collision(s) de casse dans le trunk, erreur sur tout système "
             "(aucun fichier n'a été laissé) :"] + [f"  {line}" for line in collisions]))


def _owner(rootstock: Rootstock, entries, target: Path, projected=frozenset(),
           tables=None) -> str:
    """Name the scion that put ``target`` in the trunk, ``trunk`` if none did."""
    tables = tables or {}
    relative = target.relative_to(rootstock.trunk)
    if target.is_symlink():
        pointed = os.path.normpath(os.path.join(target.parent, os.readlink(target)))
        fallback = None
        for entry in entries.values():
            key = entry.ref.key
            if key in projected:
                root = os.path.normpath(rootstock.resolve(entry.local_path))
                if pointed.startswith(root + os.sep):
                    table = tables.get(key)
                    if table is None or str(relative) in table.table:
                        return key
                    fallback = fallback or key
                continue
            stem = os.path.normpath(_stem(rootstock, entry))
            if pointed.startswith(stem + os.sep):
                return key
        return fallback or "trunk"
    if target.is_dir():
        for entry in entries.values():
            key = entry.ref.key
            if key in projected:
                table = tables.get(key)
                if table is not None and str(relative) in table.dirs:
                    return key
            elif (_stem(rootstock, entry) / relative).is_dir():
                return key
    return "trunk"


def _graft_entries(rootstock: Rootstock, chosen: list[GraftedEntry], entries,
                   projected=frozenset(), tables=None, plans=None,
                   partial: bool = False) -> list[Path]:
    """Link the ``chosen`` scions onto the trunk as it stands.

    A directory of the trunk is always a real directory: a scion directory
    meeting a file or a link is a conflict, and nothing below it is grafted, so
    that no link is ever created through another link -- that is, inside a
    clone. On conflict, what this call created is undone. ``plans`` are the
    resolved projected scions among ``chosen`` (by default, ``tables``).
    """
    tables = tables or {}
    plans = tables if plans is None else plans
    trunk = rootstock.trunk
    created_dirs: list[Path] = []
    created_links: list[Path] = []
    owners: dict[str, str] = {}
    conflicts: list[tuple[str, str, str]] = []
    excluded = 0
    try:
        planned = [(entry, *_items(rootstock, entry, plans.get(entry.ref.key)))
                   for entry in chosen]
        if projected:
            _check_case(rootstock, planned, plans, tables, partial)
        for entry, items, ignored in planned:
            excluded += ignored
            blocked: list[Path] = []
            for kind, relative, source in items:
                if any(_within(relative, top) for top in blocked):
                    continue
                target = trunk / relative
                if kind == "dir":
                    if target.is_symlink() or (os.path.lexists(target) and not target.is_dir()):
                        first = owners.get(str(relative)) or _owner(
                            rootstock, entries, target, projected, tables)
                        conflicts.append((str(relative), first, entry.ref.key))
                        blocked.append(relative)
                        continue
                    _mkdir(target, created_dirs)
                    owners.setdefault(str(relative), entry.ref.key)
                    continue
                if os.path.lexists(target):
                    first = owners.get(str(relative)) or _owner(
                        rootstock, entries, target, projected, tables)
                    conflicts.append((str(relative), first, entry.ref.key))
                    continue
                target.symlink_to(relative_link(source, target))
                created_links.append(target)
                owners[str(relative)] = entry.ref.key
        if conflicts:
            raise ScionError(_report(conflicts))
    except ScionError:
        _rollback(created_links, created_dirs)
        raise
    if excluded:
        log.info("greffe : %d chemin(s) ignoré(s) par git, non greffé(s) (détail avec -v)", excluded)
    return created_links


def _report(conflicts: list[tuple[str, str, str]]) -> str:
    lines = [f"{len(conflicts)} conflit(s) de greffe, aucun fichier n'a été laissé :"]
    lines += [f"  {path} : déjà fourni par « {first} », réclamé par « {second} »"
              for path, first, second in conflicts]
    return "\n".join(lines)


def ungraft(rootstock: Rootstock, force: bool = False) -> None:
    """Empty the trunk without ever following a link.

    A regular file in the trunk is user data, not a graft: it stops the ungraft
    unless ``force`` is given, in which case it is kept and everything else goes.
    A file the rootstock tolerates is not user data: it goes with the rest.
    """
    trunk = rootstock.trunk
    if not trunk.is_dir():
        return
    for path in _check_stray(rootstock, force):
        path.unlink()
        log.debug("supprimé (toléré) : %s", path.relative_to(trunk))
    for dirpath, dirnames, filenames in os.walk(trunk, topdown=False, followlinks=False):
        for name in filenames + dirnames:
            path = Path(dirpath) / name
            if path.is_symlink():
                path.unlink()
            elif path.is_dir():
                try:
                    path.rmdir()
                except OSError:
                    pass


def regraft(rootstock: Rootstock, force: bool = False, prepare=None) -> int:
    """Empty the trunk and graft it again; on failure, put back what it held.

    ``prepare``, called first, may rewrite the grafted list. Whatever fails --
    ``prepare``, the ungraft or the graft -- the trunk's links and directories
    and the grafted list are restored as they were found, and the error goes
    on, its message saying so.
    """
    state = _snapshot(rootstock)
    try:
        if prepare is not None:
            prepare()
        plans = _projections(rootstock, read_grafted(rootstock.grafted_list))[1]
        ungraft(rootstock, force=force)
        return graft(rootstock, plans)
    except BaseException as exc:
        note = _put_back(rootstock, state)
        if isinstance(exc, ScionError):
            exc.args = (f"{exc}\n{note}", *exc.args[1:])
        else:
            log.error("%s", note)
        raise


def _snapshot(rootstock: Rootstock):
    """The grafted list's text, and the trunk's directories and links."""
    trunk = rootstock.trunk
    grafted = rootstock.grafted_list.read_text() if rootstock.grafted_list.exists() else None
    directories: list[Path] = []
    links: list[tuple[Path, str]] = []
    if trunk.is_dir():
        for dirpath, dirnames, filenames in os.walk(trunk, followlinks=False):
            for name in dirnames + filenames:
                path = Path(dirpath) / name
                if path.is_symlink():
                    links.append((path, os.readlink(path)))
                elif path.is_dir():
                    directories.append(path)
    return grafted, directories, links


def _put_back(rootstock: Rootstock, state) -> str:
    """Restore what :func:`_snapshot` recorded; return a line saying so."""
    grafted, directories, links = state
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
    for path, target in links:
        if not os.path.lexists(path):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.symlink_to(target)
    if grafted is not None:
        rootstock.grafted_list.write_text(grafted)
    broken = sum(1 for path, _ in links if not path.exists())
    note = (f"trunk rétabli dans son état antérieur ({len(links)} lien(s)), "
            f"{GRAFTED_LIST} comprise")
    if broken:
        note += (f" ; {broken} lien(s) pointent vers des fichiers retirés des clones "
                 "depuis : la prochaine greffe réussie les corrige")
    return note


def _check_stray(rootstock: Rootstock, force: bool) -> list[Path]:
    """Stop on a regular file of the trunk, unless ``force`` is given.

    Files the rootstock tolerates never stop anything: they are returned, for
    the caller to remove.
    """
    trunk = rootstock.trunk
    patterns = _tolerated_patterns(rootstock)
    stray: list[Path] = []
    tolerated: list[Path] = []
    for dirpath, _, filenames in os.walk(trunk, followlinks=False):
        for name in filenames:
            path = Path(dirpath) / name
            if path.is_symlink() or (Path(dirpath) == trunk and name == GRAFTED_LIST):
                continue
            (tolerated if _is_tolerated(name, patterns) else stray).append(path)
    if stray and not force:
        listing = "\n".join(f"  {path.relative_to(trunk)}" for path in stray)
        raise ScionError(
            f"le trunk {trunk} contient des fichiers qui ne sont pas des greffes :\n"
            f"{listing}\nDéplacez-les, déclarez leur motif dans {rootstock.tolerated}, "
            "ou utilisez --force pour les conserver et dégreffer le reste"
        )
    return tolerated


def _tolerated_patterns(rootstock: Rootstock) -> list[str]:
    """The patterns of the rootstock's tolerated file; none when it is absent."""
    try:
        text = rootstock.tolerated.read_text()
    except FileNotFoundError:
        return []
    lines = (line.strip() for line in text.splitlines())
    return [line for line in lines if line and not line.startswith("#")]


def _is_tolerated(name: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns)


def _drop_tolerated(directory: Path, patterns: list[str]) -> None:
    """Remove the tolerated files of ``directory`` when they are all it holds."""
    try:
        children = list(directory.iterdir())
    except OSError:
        return
    if not all(child.is_file() and not child.is_symlink()
               and _is_tolerated(child.name, patterns) for child in children):
        return
    for child in children:
        child.unlink()
        log.debug("supprimé (toléré) : %s", child)


# --------------------------------------------------------------------------
# one scion at a time
# --------------------------------------------------------------------------
def _entry(entries, key: str) -> GraftedEntry:
    """Look a scion up by ``shelf@name``, the form ``scion git --key`` uses."""
    entry = entries.get(key.replace("@", "/", 1))
    if entry is None:
        raise ScionError(f"scion « {key} » absent de la liste greffée")
    return entry


def _unlink(rootstock: Rootstock, chosen: list[GraftedEntry], entries=None,
            projected=frozenset(), tables=None) -> list[tuple[Path, str]]:
    """Remove from the trunk every link pointing into a ``chosen`` scion.

    Links are recognised by their target, not by the scion's current content,
    so that a file deleted from the clone loses its link too. A projected
    scion owns the links into its clone, except those another projected scion
    sharing the clone claims in its table. Returns what was removed, as
    ``(link, target)``, so that it can be put back.
    """
    tables = tables or {}
    chosen_keys = {entry.ref.key for entry in chosen}
    prefixes: list[tuple[str, set[str]]] = []
    for entry in chosen:
        if entry.ref.key not in projected:
            prefixes.append((os.path.normpath(_stem(rootstock, entry)) + os.sep, set()))
            continue
        root = os.path.normpath(rootstock.resolve(entry.local_path))
        claimed: set[str] = set()
        for key, other in (entries or {}).items():
            if (key in projected and key not in chosen_keys and key in tables
                    and os.path.normpath(rootstock.resolve(other.local_path)) == root):
                claimed |= set(tables[key].table)
        prefixes.append((root + os.sep, claimed))
    removed: list[tuple[Path, str]] = []
    for dirpath, dirnames, filenames in os.walk(rootstock.trunk, followlinks=False):
        for name in filenames + dirnames:
            path = Path(dirpath) / name
            if not path.is_symlink():
                continue
            target = os.readlink(path)
            pointed = os.path.normpath(os.path.join(dirpath, target))
            for prefix, claimed in prefixes:
                if pointed.startswith(prefix):
                    if not claimed or str(path.relative_to(rootstock.trunk)) not in claimed:
                        removed.append((path, target))
                    break
    for path, _ in removed:
        path.unlink()
    return removed


def _restore(removed: list[tuple[Path, str]]) -> None:
    for path, target in removed:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(target)


def _prune(rootstock: Rootstock, candidates, providers, projected=frozenset(),
           tables=None) -> None:
    """Remove the candidate directories left empty that no provider grafts.

    A directory a remaining scion declares -- even an empty one -- stays; one
    holding nothing but tolerated files goes, and so do they.
    """
    tables = tables or {}
    trunk = rootstock.trunk
    stems = [_stem(rootstock, entry) for entry in providers if entry.ref.key not in projected]
    projected_dirs = [tables[entry.ref.key].dirs for entry in providers
                      if entry.ref.key in projected and entry.ref.key in tables]
    patterns = _tolerated_patterns(rootstock)
    every: set[Path] = set()
    for directory in candidates:
        while directory != trunk and trunk in directory.parents:
            every.add(directory)
            directory = directory.parent
    for directory in sorted(every, key=lambda p: len(p.parts), reverse=True):
        relative = directory.relative_to(trunk)
        if any((stem / relative).is_dir() for stem in stems):
            continue
        if any(str(relative) in dirs for dirs in projected_dirs):
            continue
        _drop_tolerated(directory, patterns)
        try:
            directory.rmdir()
        except OSError:
            pass


def graft_scions(rootstock: Rootstock, keys: list[str], force: bool = False) -> int:
    """Re-graft only the named scions; the rest of the trunk is left as it is.

    Their links are removed and created again from their current content. On
    conflict with another scion, the call is undone and the old links come back.
    A projected scion is resolved and its clone checked before anything moves.
    """
    entries = read_grafted(rootstock.grafted_list)
    chosen = [_entry(entries, key) for key in keys]
    rootstock.trunk.mkdir(parents=True, exist_ok=True)
    _check_stray(rootstock, force)
    chosen_keys = {entry.ref.key for entry in chosen}
    projected, tables = _projections(rootstock, entries, strict=chosen_keys)
    plans = {key: table for key, table in tables.items() if key in chosen_keys}
    removed = _unlink(rootstock, chosen, entries, projected, tables)
    try:
        links = _graft_entries(rootstock, chosen, entries, projected, tables, plans,
                               partial=True)
    except ScionError:
        _restore(removed)
        raise
    _prune(rootstock, [path.parent for path, _ in removed], entries.values(), projected, tables)
    log.info("greffe partielle : %d feuilles liées dans %s", len(links), rootstock.trunk)
    return len(links)


def remove(rootstock: Rootstock, key: str, purge: bool = False, force: bool = False) -> None:
    """Take one scion off the trunk and out of the grafted list.

    With ``purge``, its clone goes too -- only when scion made it, nothing else
    uses it and it holds no work that exists nowhere else. A carrier takes the
    projected scions it carries with it; their clones stay.
    """
    entries = read_grafted(rootstock.grafted_list)
    entry = _entry(entries, key)
    carrier = rootstock.store(_carrier_dot(rootstock, entry))
    carried = [other for other in entries.values()
               if other.carrier == carrier and other.ref.key != entry.ref.key]
    clone = _purgeable_clone(rootstock, entry, entries) if purge else None
    _check_stray(rootstock, force)
    projected, tables = _projections(rootstock, entries, strict=set())

    leaving = [entry] + carried
    removed = _unlink(rootstock, leaving, entries, projected, tables)
    candidates = [path.parent for path, _ in removed]
    for gone in leaving:
        del entries[gone.ref.key]
        if gone.ref.key in projected:
            table = tables.get(gone.ref.key)
            if table is not None:
                candidates += [rootstock.trunk / directory for directory in table.dirs]
            continue
        stem = _stem(rootstock, gone)
        if stem.is_dir():
            ignored = _ignored(rootstock, gone, stem)
            candidates += [rootstock.trunk / relative
                           for kind, relative in _walk(stem, ignored) if kind == "dir"]
    _prune(rootstock, candidates, entries.values(), projected, tables)
    write_grafted(rootstock.grafted_list, entries.values())
    log.info("scion %s retiré : %d feuilles", entry.ref.key, len(removed))
    if carried:
        log.info("clés projetées retirées avec leur porteur %s : %s", entry.ref.key,
                 ", ".join(other.ref.key for other in carried))

    if clone is not None:
        shutil.rmtree(clone)
        parent = clone.parent
        while parent != rootstock.depots and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent
        log.info("clone %s supprimé", clone)


def _inside(path: Path, base: Path) -> bool:
    return path == base or base in path.parents


def _purgeable_clone(rootstock: Rootstock, entry: GraftedEntry, entries) -> Path:
    ref = entry.ref
    clone = rootstock.depots / ref.shelf / ref.prefix / ref.version
    local = rootstock.resolve(entry.local_path)
    if not _inside(local, clone):
        raise ScionError(
            f"scion « {ref.key} » : {local} n'a pas été cloné par scion "
            f"(attendu sous {clone}) ; --purge refusé"
        )
    sharing = [
        other.ref.key for other in entries.values()
        if other.ref.key != ref.key and _inside(rootstock.resolve(other.local_path), clone)
    ]
    if sharing:
        raise ScionError(
            f"clone {clone} partagé avec {', '.join(sharing)} ; --purge refusé"
        )
    if not (clone / ".git").exists():
        raise ScionError(f"{clone} n'est pas un clone git ; --purge refusé")
    if gitops.status_porcelain(clone):
        raise ScionError(f"{clone} contient des modifications non commitées ; --purge refusé")
    if gitops.run(["log", "--branches", "--not", "--remotes", "--oneline"], cwd=clone).strip():
        raise ScionError(f"{clone} contient des commits absents de l'amont ; --purge refusé")
    return clone
