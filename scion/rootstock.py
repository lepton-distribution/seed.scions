"""Locating a rootstock and resolving paths against it.

A rootstock is the directory holding ``.scion.rootstock.signature``. Everything
else derives from it, and no environment variable is read or written: a local
path in a seed is either absolute or relative to the rootstock.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .errors import ScionError
from .model import GRAFTED_LIST

SIGNATURE = ".scion.rootstock.signature"
DEPOTS_DIR = "depots"
STEM_DIR = "scion"
HIDDEN_DIR = ".scion"
DEFAULT_TRUNK = "trunk"

#: created by ``rootstock-install``; the seeds refer to these by relative path.
INSTALL_LAYOUT = (
    f"{DEPOTS_DIR}/origin/{STEM_DIR}/sources",
    f"{DEPOTS_DIR}/generation/building/{STEM_DIR}/building/projects",
    f"{DEPOTS_DIR}/generation/building/{STEM_DIR}/building/staging/lib",
    f"{DEPOTS_DIR}/generation/building/{STEM_DIR}/building/output",
)


@dataclass(frozen=True)
class Rootstock:
    path: Path
    trunk_name: str

    @property
    def depots(self) -> Path:
        return self.path / DEPOTS_DIR

    @property
    def trunk(self) -> Path:
        return self.path / self.trunk_name

    @property
    def grafted_list(self) -> Path:
        return self.trunk / GRAFTED_LIST

    def resolve(self, location: str) -> Path:
        """Turn a local path from a seed or from the grafted list into a real one."""
        if "$" in location:
            head, _, tail = location.partition("/")
            hint = tail if head.startswith("$") and tail else "depots/..."
            raise ScionError(
                f"chemin local « {location} » : les variables d'environnement ne sont "
                f"pas supportées. Utilisez un chemin relatif au rootstock, ici « {hint} »"
            )
        path = Path(location)
        return path if path.is_absolute() else self.path / path

    def store(self, path: Path) -> str:
        """Render a resolved path the way it is written in the grafted list."""
        path = Path(path)
        try:
            return str(path.relative_to(self.path))
        except ValueError:
            return str(path)


def discover(explicit: str | None = None, start: Path | None = None,
             trunk: str | None = None) -> Rootstock:
    """Find the rootstock to work on, and the name of its trunk.

    Without an explicit path, the search walks up from ``start`` (the current
    directory) to the first directory carrying the signature. Nothing else is
    ever taken as a hint.
    """
    if explicit is not None:
        path = Path(explicit).resolve()
        if not (path / SIGNATURE).exists():
            raise ScionError(f"{path} n'est pas un rootstock : {SIGNATURE} absent")
    else:
        path = None
        current = Path(start or Path.cwd()).resolve()
        for candidate in (current, *current.parents):
            if (candidate / SIGNATURE).exists():
                path = candidate
                break
        if path is None:
            raise ScionError(
                f"aucun rootstock trouvé depuis {current} : {SIGNATURE} introuvable "
                "en remontant. Lancez « scion rootstock-install » dans un répertoire vide"
            )
    return Rootstock(path, trunk or find_trunk(path))


def find_trunk(path: Path) -> str:
    """Name the trunk: the child of the rootstock holding the grafted list."""
    candidates = sorted(
        child.name
        for child in path.iterdir()
        if child.is_dir() and (child / GRAFTED_LIST).exists()
    )
    if not candidates:
        raise ScionError(
            f"rootstock {path} non initialisé : aucun répertoire ne contient "
            f"{GRAFTED_LIST}. Lancez « scion rootstock-install »"
        )
    if len(candidates) > 1:
        raise ScionError(
            f"trunk ambigu dans {path} : {', '.join(candidates)}. "
            "Précisez-le avec --trunk"
        )
    return candidates[0]


def install(path: Path, trunk_name: str = DEFAULT_TRUNK) -> Rootstock:
    """Lay out an empty directory as a rootstock."""
    path = Path(path).resolve()
    if any(path.iterdir()):
        raise ScionError(f"le répertoire d'installation {path} n'est pas vide")
    (path / SIGNATURE).touch()
    (path / trunk_name).mkdir()
    (path / trunk_name / GRAFTED_LIST).touch()
    for relative in INSTALL_LAYOUT:
        (path / relative).mkdir(parents=True, exist_ok=True)
    return Rootstock(path, trunk_name)


def relative_link(source: Path, link: Path) -> str:
    """The target to store in ``link`` so that it points at ``source``.

    Computed from the directory holding the link, never from the rootstock, so
    that the whole rootstock can be moved or bind-mounted elsewhere.
    """
    return os.path.relpath(source, link.parent)
