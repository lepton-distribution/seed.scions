"""Conservation mirrors: the ``.scion.mirrors`` declaration (doc/projection-miroir.md, part B)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from .errors import ScionError
from .model import MIRRORS, numbered_lines, read_grafted
from .projection import has_projections
from .rootstock import HIDDEN_DIR, STEM_DIR, Rootstock

def is_remote(location: str) -> bool:
    return bool(urlparse(location).netloc)


# --------------------------------------------------------------------------
# declaration
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Mirror:
    """One line of ``.scion.mirrors``."""

    url: str
    upstream: str
    where: str


def read_mirrors(path: Path) -> list[Mirror]:
    """Read one ``.scion.mirrors``; any malformed line is an error (M-D3)."""
    found: list[Mirror] = []
    errors: list[str] = []
    for number, f in numbered_lines(path):
        where = f"{path}:{number}"
        if len(f) != 2:
            errors.append(f"{where} : 2 champs attendus (<url du miroir> <url de l'amont>), "
                          f"{len(f)} trouvé(s)")
            continue
        local = [value for value in f if not is_remote(value)]
        if local:
            errors.append(f"{where} : « {local[0]} » n'est pas une URL distante")
            continue
        found.append(Mirror(f[0], f[1], where))
    if errors:
        raise ScionError("\n".join(errors))
    return found


def upstream_of(dot: Path, url: str) -> str | None:
    """The upstream ``dot`` declares for the mirror ``url``, read leniently (M-D5).

    Only used to complete an error message: an unreadable file or a malformed
    line is skipped, and the answer never changes which URL is cloned (M-D2).
    """
    path = Path(dot) / MIRRORS
    if not path.is_file():
        return None
    try:
        lines = numbered_lines(path)
    except ScionError:
        return None
    for _, f in lines:
        if len(f) == 2 and f[0] == url:
            return f[1]
    return None


def hint(dot: Path, url: str) -> str:
    """The suggestion appended to a failure on ``url``; empty if it is no mirror."""
    upstream = upstream_of(dot, url)
    if upstream is None:
        return ""
    return (f" ; {url} est déclaré comme miroir de {upstream} dans {Path(dot) / MIRRORS} : "
            "lancez « scion mirror-sync »")


def _dots(rootstock: Rootstock, seed: Path | None) -> list[Path]:
    """The ``.scion/`` whose mirrors are processed: seeds, then their carriers (M-C1)."""
    entries = read_grafted(rootstock.grafted_list)
    if seed is not None:
        seeds = [Path(seed).resolve()]
    else:
        seeds = []
        for entry in entries.values():
            if entry.seed_dot_scion:
                resolved = rootstock.resolve(entry.seed_dot_scion).resolve()
                if resolved not in seeds:
                    seeds.append(resolved)
    dots: list[Path] = []
    for dot in seeds:
        if dot not in dots:
            dots.append(dot)
        for entry in entries.values():
            if entry.carrier or not entry.seed_dot_scion:
                continue
            if rootstock.resolve(entry.seed_dot_scion).resolve() != dot:
                continue
            carrier = (rootstock.resolve(entry.local_path) / STEM_DIR / HIDDEN_DIR).resolve()
            if has_projections(carrier) and carrier not in dots:
                dots.append(carrier)
    return dots


def declared(rootstock: Rootstock, seed: Path | None = None) -> list[Mirror]:
    """Every mirror to process, each once; declaration errors all together."""
    mirrors: list[Mirror] = []
    errors: list[str] = []
    for dot in _dots(rootstock, seed):
        if (dot / MIRRORS).is_file():
            try:
                mirrors += read_mirrors(dot / MIRRORS)
            except ScionError as exc:
                errors.append(str(exc))
    first: dict[str, Mirror] = {}
    for mirror in mirrors:
        known = first.setdefault(mirror.url, mirror)
        if known.upstream != mirror.upstream:
            errors.append(f"{mirror.where} : miroir {mirror.url} associé à deux amonts, "
                          f"{known.upstream} ({known.where}) et {mirror.upstream}")
    if errors:
        raise ScionError("déclaration des miroirs incorrecte :\n" + "\n".join(errors))
    return list(first.values())
