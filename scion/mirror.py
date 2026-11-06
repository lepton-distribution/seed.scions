"""Conservation mirrors: ``.scion.mirrors`` and ``scion mirror-sync``.

A mirror is a remote copy of an upstream repository that only ever moves
forward: branches by fast-forward, new branches and tags added, nothing
deleted, rewritten or moved. What the upstream does otherwise is reported,
never propagated (doc/projection-miroir.md, part B).

The work happens in a bare repository per mirror, under ``depots/.mirrors/``:
``refs/heads/*`` and ``refs/tags/*`` there are the mirror's, the upstream's are
fetched into ``refs/amont/*``. Each reference to send is then pushed by name.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from . import gitops
from .errors import GitError, ScionError, UsageError
from .model import MIRRORS, numbered_lines, read_grafted
from .projection import has_projections
from .rootstock import DEPOTS_DIR, HIDDEN_DIR, STEM_DIR, Rootstock

log = logging.getLogger(__name__)

WORK_DIR = ".mirrors"
UPSTREAM = "amont"
UPSTREAM_SPACE = f"refs/{UPSTREAM}/"
#: what is fetched from each side; nothing else is ever looked at (M-C3)
MIRROR_FETCH = ("+refs/heads/*:refs/heads/*", "+refs/tags/*:refs/tags/*")
UPSTREAM_FETCH = (f"+refs/heads/*:{UPSTREAM_SPACE}heads/*",
                  f"+refs/tags/*:{UPSTREAM_SPACE}tags/*")


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


def select(mirrors: list[Mirror], urls: list[str]) -> list[Mirror]:
    """Only the mirrors named by ``urls``, if any; an unknown one is a usage error."""
    if not urls:
        return mirrors
    known = {mirror.url: mirror for mirror in mirrors}
    unknown = [url for url in urls if url not in known]
    if unknown:
        raise UsageError("miroir(s) non déclaré(s) : " + ", ".join(unknown))
    return [known[url] for url in dict.fromkeys(urls)]


# --------------------------------------------------------------------------
# synchronisation
# --------------------------------------------------------------------------
@dataclass
class Report:
    url: str
    sent: list[str] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)

    def signal(self, text: str) -> None:
        self.signals.append(text)
        log.warning("miroir %s : %s", self.url, text)


def work_dir(rootstock: Rootstock, url: str) -> Path:
    """``depots/.mirrors/<host>/<path>``: host without user nor port, path as is (M-C2)."""
    parsed = urlparse(url)
    return rootstock.path / DEPOTS_DIR / WORK_DIR / (parsed.hostname or "") / parsed.path.lstrip("/")


def _configure(work: Path, mirror: Mirror) -> None:
    """The work repository's remotes, set again at each pass: plain fetches, no mirror push."""
    def replace(key: str, values) -> None:
        gitops.run(["config", "--replace-all", key, values[0]], cwd=work)
        for value in values[1:]:
            gitops.run(["config", "--add", key, value], cwd=work)

    try:
        gitops.run(["config", "--unset-all", "remote.origin.mirror"], cwd=work)
    except GitError:
        pass  # already unset
    gitops.run(["config", "remote.origin.url", mirror.url], cwd=work)
    replace("remote.origin.fetch", MIRROR_FETCH)
    gitops.run(["config", f"remote.{UPSTREAM}.url", mirror.upstream], cwd=work)
    replace(f"remote.{UPSTREAM}.fetch", UPSTREAM_FETCH)
    gitops.run(["config", f"remote.{UPSTREAM}.tagOpt", "--no-tags"], cwd=work)


def _label(name: str) -> str:
    kind, _, short = name.partition("/")
    return f"branche « {short} »" if kind == "heads" else f"tag « {short} »"


def _agreed(name: str, word: str) -> str:
    """``word`` agreed with the reference: feminine for a branch, masculine for a tag."""
    return word + "e" if name.startswith("heads/") else word


def _plan(work: Path, report: Report) -> list[tuple[str, str]]:
    """``(reference, reason)`` to send; everything else reported or skipped (B.3)."""
    mine = gitops.refs(work, "refs/")
    theirs = gitops.refs(work, UPSTREAM_SPACE)
    plan: list[tuple[str, str]] = []
    for name in sorted(set(mine) | set(theirs)):
        label = _label(name)
        branch = name.startswith("heads/")
        here, there = mine.get(name), theirs.get(name)
        if here is None:
            plan.append((name, "nouvelle" if branch else "nouveau"))          # M-R1, M-R6
        elif there is None:                                                    # M-R5, M-R9
            report.signal(f"{label} {_agreed(name, 'absent')} de l'amont : "
                          f"{_agreed(name, 'conservé')} dans le miroir ({here[1][:7]})")
        elif here[0] == there[0]:                                              # M-R3, M-R7
            log.debug("miroir %s : %s identique", report.url, label)
        elif branch:
            if gitops.is_ancestor(work, here[0], there[0]):                    # M-R2
                plan.append((name, f"avance rapide {here[0][:7]} -> {there[0][:7]}"))
            else:                                                              # M-R4
                report.signal(f"{label} non envoyée : le miroir ({here[0][:7]}) n'est pas un "
                              f"ancêtre de l'amont ({there[0][:7]}) ; historique réécrit, ou "
                              "miroir en avance")
        else:                                                                  # M-R8
            same = " ; même commit, objet de tag différent" if here[1] == there[1] else ""
            report.signal(f"{label} déplacé dans l'amont, non propagé : miroir {here[1][:7]}, "
                          f"amont {there[1][:7]}{same}")
    return plan


def _push(work: Path, mirror: Mirror, plan: list[tuple[str, str]], report: Report) -> None:
    """One push naming every reference, never forced (M-C4); refusals are reports."""
    specs = [f"{UPSTREAM_SPACE}{name}:refs/{name}" for name, _ in plan]
    try:
        out = gitops.run(["push", "--porcelain", mirror.url, *specs], cwd=work)
        failure = None
    except GitError as exc:
        out, failure = exc.stdout, exc
    status: dict[str, tuple[str, str]] = {}
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and ":" in parts[1]:
            status[parts[1].partition(":")[2]] = (parts[0], parts[2] if len(parts) > 2 else "")
    if failure is not None and not status:
        report.signal(f"envoi impossible : {failure}")
        return
    for name, reason in plan:
        flag, summary = status.get(f"refs/{name}", ("?", "absente du compte rendu de git"))
        if flag in (" ", "*"):
            report.sent.append(name)
            log.info("miroir %s : %s %s (%s)", report.url, _label(name),
                     _agreed(name, "envoyé"), reason)
        elif flag == "=":
            log.debug("miroir %s : %s déjà à jour", report.url, _label(name))
        else:
            report.signal(f"{_label(name)} {_agreed(name, 'refusé')} par le miroir : {summary}")


def sync_one(rootstock: Rootstock, mirror: Mirror, dry_run: bool = False) -> Report:
    """Bring one mirror forward; network failures become reports (M-C5)."""
    report = Report(mirror.url)
    work = work_dir(rootstock, mirror.url)
    if not (work / "config").is_file():
        work.parent.mkdir(parents=True, exist_ok=True)
        try:
            gitops.run(["clone", "--quiet", "--mirror", mirror.url, str(work)])
        except GitError as exc:
            report.signal(f"miroir inaccessible : {exc}")
            return report
    _configure(work, mirror)
    for remote, what in (("origin", "miroir"), (UPSTREAM, "amont")):
        try:
            gitops.run(["fetch", "--quiet", "--prune", "--no-tags", remote], cwd=work)
        except GitError as exc:
            report.signal(f"{what} inaccessible : {exc}")
            return report
    plan = _plan(work, report)
    if dry_run:
        for name, reason in plan:
            report.sent.append(name)
            log.info("miroir %s : %s à envoyer (%s)", report.url, _label(name), reason)
    elif plan:
        _push(work, mirror, plan, report)
    return report


def sync(rootstock: Rootstock, mirrors: list[Mirror], dry_run: bool = False) -> list[Report]:
    """Every mirror in turn, then one summary line each (M-K1)."""
    if not mirrors:
        log.info("aucun miroir déclaré")
        return []
    reports = [sync_one(rootstock, mirror, dry_run) for mirror in mirrors]
    verb = "à envoyer" if dry_run else "envoyée(s)"
    for report in reports:
        log.info("miroir %s : %d référence(s) %s, %d signalement(s)",
                 report.url, len(report.sent), verb, len(report.signals))
    return reports
