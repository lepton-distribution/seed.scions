"""The ``.scion.*`` file formats and the version comparison that drives them.

The formats are the contract with existing seeds and are reproduced as they are:
fields separated by any run of spaces and tabs, ``#`` starting a comment, lines
with too few fields silently ignored.
"""

from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

from .errors import ScionError

RAMIFICATIONS = ".scion.ramifications"
SOURCES_LIST = ".scion.sources.list"
GRAFTED_LIST = ".scion.grafted.list"

_WHITESPACE = re.compile(r"[ \t\n]+")


def fields(line: str) -> list[str]:
    """Split one line into its fields, comment and padding removed."""
    return _WHITESPACE.sub(" ", line).split("#", 1)[0].split()


# --------------------------------------------------------------------------
# version comparison
# --------------------------------------------------------------------------
def _preprocess(v: str, separator: str, ignorecase: bool) -> list:
    if ignorecase:
        v = v.lower()
    return [
        int(x)
        if x.isdigit()
        else [int(y) if y.isdigit() else y for y in re.findall(r"\d+|[a-zA-Z]+", x)]
        for x in v.split(separator)
    ]


def compare(a: str, b: str, separator: str = ".", ignorecase: bool = True) -> int:
    """Order two version strings; 0 when they are equal *or* not comparable.

    Kept bug-for-bug: ``1.0`` and ``beta13`` decompose into an int and a list,
    which Python refuses to order, and the answer is then "equal" rather than an
    exception. Seeds in the wild rely on that leniency.
    """
    left = _preprocess(a, separator, ignorecase)
    right = _preprocess(b, separator, ignorecase)
    try:
        return (left > right) - (left < right)
    except TypeError:
        return 0


# --------------------------------------------------------------------------
# entries
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class ScionRef:
    """A scion named ``shelf prefix[::suffix] version``."""

    shelf: str
    prefix: str
    suffix: str | None
    version: str

    @classmethod
    def parse(cls, shelf: str, name: str, version: str) -> ScionRef:
        prefix, separator, suffix = name.partition("::")
        return cls(shelf, prefix, suffix if separator else None, version)

    @property
    def name(self) -> str:
        return self.prefix if self.suffix is None else f"{self.prefix}::{self.suffix}"

    @property
    def key(self) -> str:
        """Identity of the scion, version excluded -- one entry per key."""
        return f"{self.shelf}/{self.name}"


@dataclass(frozen=True)
class SourceEntry:
    """One line of ``.scion.sources.list``."""

    ref: ScionRef
    location: str
    subpath: str = ""


@dataclass(frozen=True)
class GraftedEntry:
    """One line of ``.scion.grafted.list``.

    ``local_path`` and ``seed_dot_scion`` are relative to the rootstock whenever
    they sit inside it, so that the rootstock can be moved or committed.
    """

    ref: ScionRef
    local_path: str
    seed_dot_scion: str = ""

    def serialize(self) -> str:
        line = f"{self.ref.shelf} {self.ref.name} {self.ref.version} {self.local_path}"
        return f"{line} {self.seed_dot_scion}" if self.seed_dot_scion else line


# --------------------------------------------------------------------------
# readers and writers
# --------------------------------------------------------------------------
def _lines(path: Path) -> list[list[str]]:
    try:
        text = Path(path).read_text()
    except OSError as exc:
        raise ScionError(f"fichier illisible : {path} ({exc.strerror})") from exc
    return [f for f in (fields(line) for line in text.splitlines()) if f]


def read_ramifications(path: Path) -> list[ScionRef]:
    return [
        ScionRef.parse(f[0], f[1], f[2]) for f in _lines(path) if len(f) >= 3
    ]


def read_sources(path: Path) -> list[SourceEntry]:
    return [
        SourceEntry(ScionRef.parse(f[0], f[1], f[2]), f[3], f[4] if len(f) > 4 else "")
        for f in _lines(path)
        if len(f) >= 4
    ]


def read_grafted(path: Path) -> OrderedDict[str, GraftedEntry]:
    """Read the grafted list; a missing file simply means nothing is grafted."""
    entries: OrderedDict[str, GraftedEntry] = OrderedDict()
    if not Path(path).exists():
        return entries
    for f in _lines(path):
        if len(f) < 4:
            continue
        entry = GraftedEntry(
            ScionRef.parse(f[0], f[1], f[2]), f[3], f[4] if len(f) > 4 else ""
        )
        entries[entry.ref.key] = entry
    return entries


def write_grafted(path: Path, entries) -> None:
    Path(path).write_text("".join(e.serialize() + "\n" for e in entries))


def select_source(sources: list[SourceEntry], ref: ScionRef) -> SourceEntry:
    """Pick the source line a ramification entry refers to.

    An exact version match wins immediately; otherwise -- and always for the
    ``?`` version -- the highest version available for that scion is used.
    """
    chosen: SourceEntry | None = None
    for entry in sources:
        if entry.ref.key != ref.key:
            continue
        if ref.version != "?" and entry.ref.version == ref.version:
            return entry
        if chosen is None or compare(entry.ref.version, chosen.ref.version) > 0:
            chosen = entry
    if chosen is None:
        raise ScionError(
            f"scion « {ref.key} » (version {ref.version}) absent de {SOURCES_LIST}"
        )
    return chosen
