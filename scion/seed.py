"""Editing the two lists of a seed: which scions it holds, and from where.

Nothing here clones or grafts: adding a scion to a seed is followed by
``seed-clone`` and ``graft``, removing one by ``graft-remove``.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .errors import ScionError
from .graft import is_remote
from .model import (
    RAMIFICATIONS,
    SOURCES_LIST,
    ScionRef,
    read_ramifications,
    read_sources,
    rewrite_key,
)

log = logging.getLogger(__name__)


def parse_key(key: str) -> tuple[str, str]:
    """Split ``shelf@prefix[::suffix]``, the form ``scion git --key`` uses."""
    shelf, separator, name = key.partition("@")
    if not (separator and shelf and name):
        raise ScionError(f"clé « {key} » invalide : forme attendue shelf@prefix::suffix")
    return shelf, name


def _check_field(label: str, value: str) -> None:
    if not value or any(c.isspace() for c in value) or "#" in value:
        raise ScionError(f"{label} « {value} » invalide : vide, blanc ou « # »")


def _holds(dot: Path, key: str) -> bool:
    sources, ramifications = dot / SOURCES_LIST, dot / RAMIFICATIONS
    return (
        sources.exists() and any(s.ref.key == key for s in read_sources(sources))
    ) or (
        ramifications.exists()
        and any(r.key == key for r in read_ramifications(ramifications))
    )


def add_scion(dot: Path, key: str, version: str, location: str, subpath: str = "",
              replace: bool = False) -> None:
    """Declare a scion in a seed: one source line and one ramification.

    A scion the seed already names is refused, unless ``replace`` is given:
    then every line of that scion is replaced.
    """
    shelf, name = parse_key(key)
    for label, value in (("version", version), ("emplacement", location)):
        _check_field(label, value)
    if subpath:
        _check_field("chemin dans le dépôt", subpath)
    for label, value in (("shelf", shelf), ("nom", name)):
        _check_field(label, value)
    if not is_remote(location) and "$" in location:
        raise ScionError(
            f"emplacement « {location} » : les variables d'environnement ne sont pas "
            "supportées. Utilisez un chemin relatif au rootstock"
        )
    ref = ScionRef.parse(shelf, name, version)
    if _holds(dot, ref.key) and not replace:
        raise ScionError(
            f"scion « {key} » déjà déclaré dans {dot} : --replace pour le remplacer"
        )
    source = "\t".join([shelf, name, version, location] + ([subpath] if subpath else []))
    rewrite_key(dot / SOURCES_LIST, ref.key, 4, source)
    rewrite_key(dot / RAMIFICATIONS, ref.key, 3, "\t".join([shelf, name, version]))
    log.info("scion %s déclaré dans %s (version %s)", ref.key, dot, version)


def remove_scion(dot: Path, key: str) -> None:
    """Forget a scion in a seed; the grafted list and the trunk are not touched."""
    shelf, name = parse_key(key)
    ref = ScionRef.parse(shelf, name, "")
    if not _holds(dot, ref.key):
        raise ScionError(f"scion « {key} » absent de {dot}")
    for filename, minimum in ((SOURCES_LIST, 4), (RAMIFICATIONS, 3)):
        if (dot / filename).exists():
            rewrite_key(dot / filename, ref.key, minimum)
    log.info("scion %s retiré de %s", ref.key, dot)
