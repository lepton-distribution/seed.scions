"""Projecting a repository that has no ``scion/``: which of its files go where.

A ``.scion.projections`` file sits in a ``.scion/`` -- a seed's, or a carrier
scion's -- next to the source and ramification lines of the scions it
projects. Each line maps files of the repository, read from git's listing of
the pinned commit and never from the disk, onto paths of the trunk::

    <shelf>  <name>  <pattern>   <destination>     # inclusion
    <shelf>  <name>  !<pattern>                    # exclusion

Unlike the historical files, a malformed line is an error, never skipped.
Every error of a file, or of a scion, is collected before it is reported.
"""

from __future__ import annotations

import fnmatch
import logging
from dataclasses import dataclass, field
from pathlib import Path

from .errors import ScionError
from .model import (
    GRAFTED_LIST,
    PROJECTIONS,
    RAMIFICATIONS,
    SOURCES_LIST,
    ScionRef,
    numbered_lines,
)

log = logging.getLogger(__name__)

#: a destination starts with this prefix, which stands for the trunk's root.
TRUNK_PREFIX = "scion/"
HIDDEN = ".scion"
_JOKERS = frozenset("*?[")

#: git modes of what a projection treats as a file: blobs and symlinks.
FILE_MODES = frozenset({"100644", "100755", "120000"})
SUBMODULE_MODE = "160000"


# --------------------------------------------------------------------------
# patterns and destinations
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Pattern:
    """A path of the repository, possibly with jokers in its last segment.

    ``kind`` is ``file`` (no joker), ``glob`` (jokers in the last segment) or
    ``tree`` (``**``, every file below ``base``). ``base`` is the directory
    the pattern walks, ``""`` for the repository's root.
    """

    text: str
    kind: str
    base: str
    last: str


@dataclass(frozen=True)
class Destination:
    """Where a pattern lands: a directory of the trunk, or a file (renamed)."""

    text: str
    path: str
    is_dir: bool


def parse_pattern(text: str) -> tuple[Pattern | None, str | None]:
    """``(pattern, None)``, or ``(None, why it is refused)``."""
    if not text:
        return None, "motif vide"
    if text.startswith("/") or text.endswith("/"):
        return None, "« / » initial ou final interdit"
    segments = text.split("/")
    if any(segment == "" for segment in segments):
        return None, "segment vide interdit"
    if any(segment in (".", "..") for segment in segments):
        return None, "segment « . » ou « .. » interdit"
    for segment in segments[:-1]:
        if "**" in segment:
            return None, "« ** » admis seulement comme dernier segment entier (d/** ou **)"
        if _JOKERS & set(segment):
            return None, "jokers admis seulement dans le dernier segment"
    last = segments[-1]
    if "**" in last and last != "**":
        return None, "« ** » admis seulement comme dernier segment entier (d/** ou **)"
    kind = "tree" if last == "**" else "glob" if _JOKERS & set(last) else "file"
    return Pattern(text, kind, "/".join(segments[:-1]), last), None


def _bad_segment(segments: list[str]) -> str | None:
    for segment in segments:
        if segment in ("", ".", ".."):
            return "segment vide, « . » ou « .. » interdit"
        if segment == HIDDEN:
            return f"segment « {HIDDEN} » interdit"
    return None


def parse_destination(text: str, pattern: Pattern) -> tuple[Destination | None, str | None]:
    """``(destination, None)``, or ``(None, why it is refused)``."""
    if not text.startswith(TRUNK_PREFIX):
        return None, f"une destination commence par « {TRUNK_PREFIX} » (racine du trunk)"
    rest = text[len(TRUNK_PREFIX):]
    is_dir = text.endswith("/")
    path = rest[:-1] if is_dir and rest else rest
    if not is_dir and pattern.kind != "file":
        return None, ("destination fichier (sans « / » final) admise seulement pour un motif "
                      "sans joker ; terminez-la par « / »")
    if path:
        why = _bad_segment(path.split("/"))
        if why:
            return None, why
    if path == GRAFTED_LIST:
        return None, f"« {TRUNK_PREFIX}{GRAFTED_LIST} » interdit"
    return Destination(text, path, is_dir), None


# --------------------------------------------------------------------------
# the file
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Line:
    """One line of a ``.scion.projections``; an exclusion has no destination."""

    file: Path
    number: int
    key: str
    pattern: Pattern
    destination: Destination | None
    fields: tuple[str, ...]

    @property
    def exclude(self) -> bool:
        return self.destination is None

    @property
    def where(self) -> str:
        return f"{self.file}:{self.number}"

    def normalized(self) -> str:
        return " ".join(self.fields)


def read_projections(path: Path) -> list[Line]:
    """Every line of ``path``; every malformed one is reported together."""
    lines: list[Line] = []
    errors: list[str] = []
    for number, f in numbered_lines(path):
        where = f"{path}:{number}"
        if len(f) == 4 and not f[2].startswith("!"):
            text, destination = f[2], f[3]
        elif len(f) == 3 and f[2].startswith("!"):
            text, destination = f[2][1:], None
        else:
            errors.append(
                f"{where} : ligne mal formée ({len(f)} champ(s)) : attendu « shelf nom motif "
                "destination » (inclusion) ou « shelf nom !motif » (exclusion)"
            )
            continue
        key = ScionRef.parse(f[0], f[1], "").key
        pattern, why = parse_pattern(text)
        if pattern is None:
            errors.append(f"{where} : clé « {key} » : motif « {text} » : {why}")
            continue
        parsed = None
        if destination is not None:
            parsed, why = parse_destination(destination, pattern)
            if parsed is None:
                errors.append(f"{where} : clé « {key} » : destination « {destination} » : {why}")
                continue
        lines.append(Line(Path(path), number, key, pattern, parsed, tuple(f)))
    if errors:
        raise ScionError(_listing(f"{len(errors)} erreur(s) dans {path} :", errors))
    return lines


def _listing(head: str, errors: list[str]) -> str:
    return "\n".join([head] + [f"  {error}" for error in errors])


# --------------------------------------------------------------------------
# a .scion/ that declares projected scions
# --------------------------------------------------------------------------
@dataclass
class DotScion:
    """The three lists of a ``.scion/``, line numbers kept."""

    dot: Path
    sources: list[tuple[int, list[str]]]
    ramifications: list[tuple[int, list[str]]]
    projections: list[Line]

    @property
    def projected(self) -> set[str]:
        """Keys with at least one inclusion line."""
        return {line.key for line in self.projections if not line.exclude}

    def lines_of(self, key: str) -> list[Line]:
        return [line for line in self.projections if line.key == key]

    def signature(self, key: str) -> tuple:
        """What two declarations of ``key`` must share to be the same one."""
        def mine(entries, minimum):
            return sorted(" ".join(f) for _, f in entries
                          if len(f) >= minimum and _key(f) == key)
        return (mine(self.sources, 4), mine(self.ramifications, 3),
                frozenset(line.normalized() for line in self.lines_of(key)))


def _key(f: list[str]) -> str:
    return ScionRef.parse(f[0], f[1], "").key


def has_projections(dot: Path) -> bool:
    return (Path(dot) / PROJECTIONS).is_file()


def read_dot(dot: Path, carrier: bool) -> DotScion:
    """Read a ``.scion/`` that holds a ``.scion.projections``, and check it.

    A projection line whose key has no source line or no ramification is an
    error. A carrier (``carrier``) declares projected scions only: any other
    key of its lists is an error too.
    """
    dot = Path(dot)
    sources = numbered_lines(dot / SOURCES_LIST) if (dot / SOURCES_LIST).exists() else []
    ramifications = (numbered_lines(dot / RAMIFICATIONS)
                     if (dot / RAMIFICATIONS).exists() else [])
    parsed = DotScion(dot, sources, ramifications, read_projections(dot / PROJECTIONS))
    source_keys = {_key(f) for _, f in sources if len(f) >= 4}
    ramified = {_key(f) for _, f in ramifications if len(f) >= 3}
    errors: list[str] = []
    reported: set[str] = set()
    for line in parsed.projections:
        missing = [name for name, keys in ((SOURCES_LIST, source_keys), (RAMIFICATIONS, ramified))
                   if line.key not in keys]
        if missing and line.key not in reported:
            reported.add(line.key)
            errors.append(f"{line.where} : clé « {line.key} » sans ligne dans "
                          f"{' ni '.join(missing)} de {dot}")
    if carrier:
        projected = parsed.projected
        for name, entries, minimum in ((SOURCES_LIST, sources, 4), (RAMIFICATIONS, ramifications, 3)):
            for number, f in entries:
                if len(f) >= minimum and _key(f) not in projected:
                    errors.append(
                        f"{dot / name}:{number} : clé « {_key(f)} » : un scion porteur ne déclare "
                        f"que des clés projetées ; ajoutez ses lignes à {PROJECTIONS} ou "
                        "déclarez-la dans la graine"
                    )
    if errors:
        raise ScionError(_listing(f"{len(errors)} erreur(s) dans {dot} :", errors))
    return parsed


# --------------------------------------------------------------------------
# resolution
# --------------------------------------------------------------------------
@dataclass
class Listing:
    """git's listing of one commit: files (with their mode), submodules, directories."""

    files: dict[str, str]
    submodules: set[str] = field(default_factory=set)
    dirs: set[str] = field(default_factory=set)

    @classmethod
    def from_tree(cls, entries: list[tuple[str, str]]) -> Listing:
        listing = cls({})
        for mode, path in entries:
            if mode == SUBMODULE_MODE:
                listing.submodules.add(path)
            elif mode in FILE_MODES:
                listing.files[path] = mode
            else:
                continue
            parts = path.split("/")
            for depth in range(1, len(parts)):
                listing.dirs.add("/".join(parts[:depth]))
        return listing


def _match(pattern: Pattern, listing: Listing) -> tuple[list[str], str | None]:
    """The files ``pattern`` designates, sorted; or why the pattern is wrong."""
    if pattern.kind == "file":
        if pattern.text in listing.files:
            return [pattern.text], None
        if pattern.text in listing.submodules:
            return [], "désigne un sous-module, qui n'est jamais projeté"
        if pattern.text in listing.dirs:
            return [], (f"désigne un répertoire : utilisez « {pattern.text}/* » ou "
                        f"« {pattern.text}/** »")
        return [], None
    prefix = pattern.base + "/" if pattern.base else ""
    found = []
    for path in listing.files:
        if not path.startswith(prefix):
            continue
        rest = path[len(prefix):]
        if pattern.kind == "tree" or ("/" not in rest and fnmatch.fnmatchcase(rest, pattern.last)):
            found.append(path)
    return sorted(found), None


def _place(line: Line, source: str) -> str:
    destination = line.destination
    if not destination.is_dir:
        return destination.path
    base = line.pattern.base
    relative = source[len(base) + 1:] if base else source
    return f"{destination.path}/{relative}" if destination.path else relative


@dataclass
class Resolution:
    """The files of one projected scion: trunk path -> path in the repository."""

    key: str
    table: dict[str, str]
    dirs: set[str]

    @classmethod
    def of(cls, key: str, table: dict[str, str]) -> Resolution:
        dirs: set[str] = set()
        for path in table:
            parts = path.split("/")
            for depth in range(1, len(parts)):
                dirs.add("/".join(parts[:depth]))
        return cls(key, table, dirs)


def resolve(key: str, lines: list[Line], listing: Listing) -> Resolution:
    """Compute the files of ``key``; every error of the scion is reported at once."""
    errors: list[str] = []
    inclusions = [line for line in lines if line.key == key and not line.exclude]
    exclusions = [line for line in lines if line.key == key and line.exclude]

    def label(line: Line) -> str:
        return f"{line.where} : clé « {key} » : motif « {line.pattern.text} »"

    matched: dict[int, list[str]] = {}
    for line in inclusions + exclusions:
        found, why = _match(line.pattern, listing)
        if why:
            errors.append(f"{label(line)} : {why}")
            continue
        if not found and not line.exclude:
            errors.append(f"{label(line)} : aucun fichier de la liste git ne correspond")
            continue
        matched[id(line)] = found
    retained = {path for line in inclusions for path in matched.get(id(line), [])}
    excluded: set[str] = set()
    for line in exclusions:
        if id(line) not in matched:
            continue
        hits = set(matched[id(line)]) & retained
        if not hits:
            errors.append(f"{label(line)} : l'exclusion ne retire aucun fichier retenu "
                          "par les inclusions de la clé")
        excluded |= hits

    table: dict[str, str] = {}
    origin: dict[str, Line] = {}
    for line in inclusions:
        count = 0
        for source in matched.get(id(line), []):
            if source in excluded:
                continue
            trunk_path = _place(line, source)
            why = _bad_segment(trunk_path.split("/"))
            if why or trunk_path == GRAFTED_LIST:
                errors.append(f"{label(line)} : « {source} » donnerait le chemin du trunk "
                              f"« {trunk_path} » : {why or GRAFTED_LIST + ' interdit'}")
                continue
            count += 1
            previous = table.get(trunk_path)
            if previous is None:
                table[trunk_path] = source
                origin[trunk_path] = line
            elif previous != source:
                errors.append(
                    f"{label(line)} : « {source} » et « {previous} » "
                    f"({origin[trunk_path].where}) visent le même chemin du trunk « {trunk_path} »"
                )
        log.debug("projection %s : %s « %s » -> %d fichier(s)",
                  key, line.where, line.pattern.text, count)
    for source in sorted(excluded):
        log.debug("projection %s : exclu %s", key, source)

    resolution = Resolution.of(key, table)
    for path in sorted(set(table) & resolution.dirs):
        errors.append(f"clé « {key} » : « {path} » serait à la fois un fichier et un "
                      f"répertoire du trunk ({origin[path].where})")
    if errors:
        raise ScionError(_listing(f"{len(errors)} erreur(s) de projection de « {key} » :", errors))
    return resolution


# --------------------------------------------------------------------------
# case
# --------------------------------------------------------------------------
def case_collisions(paths: dict[str, tuple[str, bool]]) -> list[str]:
    """Trunk paths, directories included, that differ only by case.

    ``paths`` maps every trunk path -- files and their parent directories --
    to ``(key, projected)``. A group counts only when one of its paths comes
    from a projection.
    """
    groups: dict[str, list[str]] = {}
    for path in paths:
        groups.setdefault(path.casefold(), []).append(path)
    found = []
    for members in groups.values():
        if len(members) < 2 or not any(paths[m][1] for m in members):
            continue
        found.append(", ".join(f"« {m} » ({paths[m][0]})" for m in sorted(members)))
    return sorted(found)
