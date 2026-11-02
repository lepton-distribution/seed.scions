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
from .errors import ScionError
from .model import (
    GRAFTED_LIST,
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
from .rootstock import HIDDEN_DIR, STEM_DIR, Rootstock, relative_link

log = logging.getLogger(__name__)


def is_remote(location: str) -> bool:
    return bool(urlparse(location).netloc)


# --------------------------------------------------------------------------
# seeds -> grafted list
# --------------------------------------------------------------------------
def sync(rootstock: Rootstock, seed_dot_scion: Path, single_branch: bool = False,
         update: bool = False) -> None:
    """Resolve one seed into the grafted list, cloning what is missing.

    Clones are grouped by destination, so a seed declaring sixteen scions cut
    out of the same repository clones -- and pulls -- it once.
    """
    dot = Path(seed_dot_scion).resolve()
    sources = read_sources(dot / SOURCES_LIST)
    entries = read_grafted(rootstock.grafted_list)
    wanted: list[tuple[GraftedEntry, str, str]] = []

    for ref in read_ramifications(dot / RAMIFICATIONS):
        source = select_source(sources, ref)
        if is_remote(source.location):
            clone_dir = (
                rootstock.depots / source.ref.shelf / source.ref.prefix / source.ref.version
            )
        else:
            clone_dir = rootstock.resolve(source.location)
        local = clone_dir / source.subpath if source.subpath else clone_dir
        entry = GraftedEntry(source.ref, rootstock.store(local), rootstock.store(dot))

        previous = entries.get(entry.ref.key)
        if previous is not None and compare(previous.ref.version, entry.ref.version) > 0:
            log.info(
                "scion %s : la version greffée %s est plus récente que %s, conservée",
                entry.ref.key, previous.ref.version, entry.ref.version,
            )
            continue
        entries[entry.ref.key] = entry
        wanted.append(
            (entry, source.location if is_remote(source.location) else "", str(clone_dir))
        )

    _fetch(wanted, single_branch, update)
    for entry, _, _ in wanted:
        stem = rootstock.resolve(entry.local_path) / STEM_DIR
        if not stem.is_dir():
            raise ScionError(
                f"scion « {entry.ref.key} » : {stem} est absent. Vérifiez la colonne "
                f"« chemin dans le dépôt » de {SOURCES_LIST}"
            )
    rootstock.grafted_list.parent.mkdir(parents=True, exist_ok=True)
    write_grafted(rootstock.grafted_list, entries.values())


def _fetch(wanted, single_branch: bool, update: bool) -> None:
    """Clone or pull each distinct repository exactly once."""
    seen: OrderedDict[str, tuple[str, str]] = OrderedDict()
    for entry, url, clone_dir in wanted:
        if url:
            seen.setdefault(clone_dir, (url, entry.ref.version))
    for clone_dir, (url, version) in seen.items():
        destination = Path(clone_dir)
        if (destination / ".git").exists():
            if update:
                gitops.pull(destination)
        else:
            gitops.clone(url, destination, version, single_branch)


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


def graft(rootstock: Rootstock) -> int:
    """Graft every scion of the grafted list onto the trunk.

    Conflicts are all collected before anything is reported, and a conflicting
    graft leaves nothing behind: what this call created is undone.
    """
    entries = read_grafted(rootstock.grafted_list)
    if not entries:
        raise ScionError(
            f"{rootstock.grafted_list} est vide : ajoutez un seed avec « scion seed-add »"
        )
    rootstock.trunk.mkdir(parents=True, exist_ok=True)
    links = _graft_entries(rootstock, list(entries.values()), entries)
    log.info("greffe : %d feuilles liées dans %s", len(links), rootstock.trunk)
    return len(links)


def _stem(rootstock: Rootstock, entry: GraftedEntry) -> Path:
    return rootstock.resolve(entry.local_path) / STEM_DIR


def _within(relative: Path, base: Path) -> bool:
    return relative.parts[: len(base.parts)] == base.parts


def _owner(rootstock: Rootstock, entries, target: Path) -> str:
    """Name the scion that put ``target`` in the trunk, ``trunk`` if none did."""
    relative = target.relative_to(rootstock.trunk)
    if target.is_symlink():
        pointed = os.path.normpath(os.path.join(target.parent, os.readlink(target)))
        for entry in entries.values():
            stem = os.path.normpath(_stem(rootstock, entry))
            if pointed.startswith(stem + os.sep):
                return entry.ref.key
    elif target.is_dir():
        for entry in entries.values():
            if (_stem(rootstock, entry) / relative).is_dir():
                return entry.ref.key
    return "trunk"


def _graft_entries(rootstock: Rootstock, chosen: list[GraftedEntry], entries) -> list[Path]:
    """Link the ``chosen`` scions onto the trunk as it stands.

    A directory of the trunk is always a real directory: a scion directory
    meeting a file or a link is a conflict, and nothing below it is grafted, so
    that no link is ever created through another link -- that is, inside a
    clone. On conflict, what this call created is undone.
    """
    trunk = rootstock.trunk
    created_dirs: list[Path] = []
    created_links: list[Path] = []
    owners: dict[str, str] = {}
    conflicts: list[tuple[str, str, str]] = []
    excluded = 0
    try:
        for entry in chosen:
            stem = _stem(rootstock, entry)
            if not stem.is_dir():
                raise ScionError(f"scion « {entry.ref.key} » : {stem} est absent")
            ignored = _ignored(rootstock, entry, stem)
            excluded += len(ignored)
            blocked: list[Path] = []
            for kind, relative in _walk(stem, ignored):
                if any(_within(relative, top) for top in blocked):
                    continue
                target = trunk / relative
                if kind == "dir":
                    if target.is_symlink() or (os.path.lexists(target) and not target.is_dir()):
                        first = owners.get(str(relative)) or _owner(rootstock, entries, target)
                        conflicts.append((str(relative), first, entry.ref.key))
                        blocked.append(relative)
                        continue
                    _mkdir(target, created_dirs)
                    owners.setdefault(str(relative), entry.ref.key)
                    continue
                if os.path.lexists(target):
                    first = owners.get(str(relative)) or _owner(rootstock, entries, target)
                    conflicts.append((str(relative), first, entry.ref.key))
                    continue
                target.symlink_to(relative_link(stem / relative, target))
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


def _unlink(rootstock: Rootstock, chosen: list[GraftedEntry]) -> list[tuple[Path, str]]:
    """Remove from the trunk every link pointing into a ``chosen`` scion.

    Links are recognised by their target, not by the scion's current content,
    so that a file deleted from the clone loses its link too. Returns what was
    removed, as ``(link, target)``, so that it can be put back.
    """
    stems = [os.path.normpath(_stem(rootstock, entry)) + os.sep for entry in chosen]
    removed: list[tuple[Path, str]] = []
    for dirpath, dirnames, filenames in os.walk(rootstock.trunk, followlinks=False):
        for name in filenames + dirnames:
            path = Path(dirpath) / name
            if not path.is_symlink():
                continue
            target = os.readlink(path)
            pointed = os.path.normpath(os.path.join(dirpath, target))
            if any(pointed.startswith(stem) for stem in stems):
                removed.append((path, target))
    for path, _ in removed:
        path.unlink()
    return removed


def _restore(removed: list[tuple[Path, str]]) -> None:
    for path, target in removed:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(target)


def _prune(rootstock: Rootstock, candidates, providers) -> None:
    """Remove the candidate directories left empty that no provider grafts.

    A directory a remaining scion declares -- even an empty one -- stays; one
    holding nothing but tolerated files goes, and so do they.
    """
    trunk = rootstock.trunk
    stems = [_stem(rootstock, entry) for entry in providers]
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
        _drop_tolerated(directory, patterns)
        try:
            directory.rmdir()
        except OSError:
            pass


def graft_scions(rootstock: Rootstock, keys: list[str], force: bool = False) -> int:
    """Re-graft only the named scions; the rest of the trunk is left as it is.

    Their links are removed and created again from their current content. On
    conflict with another scion, the call is undone and the old links come back.
    """
    entries = read_grafted(rootstock.grafted_list)
    chosen = [_entry(entries, key) for key in keys]
    rootstock.trunk.mkdir(parents=True, exist_ok=True)
    _check_stray(rootstock, force)
    removed = _unlink(rootstock, chosen)
    try:
        links = _graft_entries(rootstock, chosen, entries)
    except ScionError:
        _restore(removed)
        raise
    _prune(rootstock, [path.parent for path, _ in removed], entries.values())
    log.info("greffe partielle : %d feuilles liées dans %s", len(links), rootstock.trunk)
    return len(links)


def remove(rootstock: Rootstock, key: str, purge: bool = False, force: bool = False) -> None:
    """Take one scion off the trunk and out of the grafted list.

    With ``purge``, its clone goes too -- only when scion made it, nothing else
    uses it and it holds no work that exists nowhere else.
    """
    entries = read_grafted(rootstock.grafted_list)
    entry = _entry(entries, key)
    clone = _purgeable_clone(rootstock, entry, entries) if purge else None
    _check_stray(rootstock, force)

    removed = _unlink(rootstock, [entry])
    del entries[entry.ref.key]
    candidates = [path.parent for path, _ in removed]
    stem = _stem(rootstock, entry)
    if stem.is_dir():
        ignored = _ignored(rootstock, entry, stem)
        candidates += [rootstock.trunk / relative
                       for kind, relative in _walk(stem, ignored) if kind == "dir"]
    _prune(rootstock, candidates, entries.values())
    write_grafted(rootstock.grafted_list, entries.values())
    log.info("scion %s retiré : %d feuilles", entry.ref.key, len(removed))

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
