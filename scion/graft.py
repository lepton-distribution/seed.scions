"""Turning seeds into a grafted list, and the grafted list into a trunk.

The trunk is disposable: every directory in it is a real directory and every
leaf is a relative symlink into ``depots/``. Nothing is ever written inside a
clone, and a moved rootstock keeps working without re-grafting.
"""

from __future__ import annotations

import logging
import os
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
def _walk(base: Path):
    """Yield ``("dir"|"leaf", path relative to base)`` for a scion.

    ``.scion/`` is skipped at every level, and a symlink committed in the
    repository is a leaf even when it points at a directory: it is copied as a
    link, never followed.
    """
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        here = Path(dirpath)
        linked = [name for name in dirnames if (here / name).is_symlink()]
        dirnames[:] = sorted(
            name for name in dirnames if name != HIDDEN_DIR and name not in linked
        )
        yield "dir", here.relative_to(base)
        for name in sorted(filenames) + sorted(linked):
            yield "leaf", (here / name).relative_to(base)


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
    trunk = rootstock.trunk
    trunk.mkdir(parents=True, exist_ok=True)

    created_dirs: list[Path] = []
    created_links: list[Path] = []
    owners: dict[str, str] = {}
    conflicts: list[tuple[str, str, str]] = []
    try:
        for entry in entries.values():
            stem = rootstock.resolve(entry.local_path) / STEM_DIR
            if not stem.is_dir():
                raise ScionError(f"scion « {entry.ref.key} » : {stem} est absent")
            for kind, relative in _walk(stem):
                target = trunk / relative
                if kind == "dir":
                    _mkdir(target, created_dirs)
                    continue
                if os.path.lexists(target):
                    conflicts.append(
                        (str(relative), owners.get(str(relative), "trunk"), entry.ref.key)
                    )
                    continue
                target.symlink_to(relative_link(stem / relative, target))
                created_links.append(target)
                owners[str(relative)] = entry.ref.key
        if conflicts:
            raise ScionError(_report(conflicts))
    except ScionError:
        _rollback(created_links, created_dirs)
        raise
    log.info("greffe : %d feuilles liées dans %s", len(created_links), trunk)
    return len(created_links)


def _report(conflicts: list[tuple[str, str, str]]) -> str:
    lines = [f"{len(conflicts)} conflit(s) de greffe, aucun fichier n'a été laissé :"]
    lines += [f"  {path} : déjà fourni par « {first} », réclamé par « {second} »"
              for path, first, second in conflicts]
    return "\n".join(lines)


def ungraft(rootstock: Rootstock, force: bool = False) -> None:
    """Empty the trunk without ever following a link.

    A regular file in the trunk is user data, not a graft: it stops the ungraft
    unless ``force`` is given, in which case it is kept and everything else goes.
    """
    trunk = rootstock.trunk
    if not trunk.is_dir():
        return
    stray = [
        Path(dirpath) / name
        for dirpath, _, filenames in os.walk(trunk, followlinks=False)
        for name in filenames
        if not (Path(dirpath) / name).is_symlink()
        and not (Path(dirpath) == trunk and name == GRAFTED_LIST)
    ]
    if stray and not force:
        listing = "\n".join(f"  {path.relative_to(trunk)}" for path in stray)
        raise ScionError(
            f"le trunk {trunk} contient des fichiers qui ne sont pas des greffes :\n"
            f"{listing}\nDéplacez-les, ou utilisez --force pour les conserver et "
            "dégreffer le reste"
        )
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
