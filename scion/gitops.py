"""Every git invocation of the tool, as argument lists -- never a shell string."""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

from .errors import GitError

log = logging.getLogger(__name__)


def run(args: list[str], cwd: Path | None = None) -> str:
    """Run one git command and return its stdout.

    Git's own output is captured rather than let through: it would interleave
    with the tool's logging, and on failure it is what the error message needs.
    """
    completed = _run(args, cwd)
    if completed.stderr:
        log.debug("%s", completed.stderr.rstrip())
    return completed.stdout


def run_verbatim(args: list[str], cwd: Path | None = None) -> tuple[str, str]:
    """Run one git command whose output is the point; return ``(stdout, stderr)``.

    On failure, both streams are carried by the :class:`GitError`.
    """
    completed = _run(args, cwd)
    return completed.stdout, completed.stderr


def _run(args: list[str], cwd: Path | None) -> subprocess.CompletedProcess:
    log.debug("git %s (cwd=%s)", " ".join(args), cwd)
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(cwd) if cwd else None,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise GitError("git est introuvable dans le PATH") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip().splitlines()
        raise GitError(
            f"échec de « git {' '.join(args)} » (code {exc.returncode})"
            + (f" : {detail[-1]}" if detail else ""),
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
        ) from exc


def clone(url: str, dest: Path, version: str = "master", single_branch: bool = False) -> None:
    """Clone ``url`` into ``dest`` and put it on ``version``.

    Without ``single_branch`` the whole repository is cloned and then checked
    out, which keeps the other branches available locally; with it, only the
    requested branch is fetched. The checkout is never skipped, ``master``
    included: the branch the origin's ``HEAD`` points to need not be the
    declared version, and a version the origin lacks is an error.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    if single_branch:
        run(["clone", "-b", version, "--single-branch", url, str(dest)])
        return
    run(["clone", url, str(dest)])
    run(["checkout", version], cwd=dest)


def pull(dest: Path) -> None:
    run(["pull"], cwd=dest)


def status_porcelain(dest: Path) -> str:
    return run(["status", "--porcelain"], cwd=dest)


def toplevel(path: Path) -> Path | None:
    """The work tree holding ``path``; ``None`` outside git, or without git."""
    try:
        return Path(run(["rev-parse", "--show-toplevel"], cwd=path).strip())
    except GitError:
        return None


_LIST_IGNORED = ["ls-files", "--others", "--ignored", "--exclude-standard", "--directory",
                 "-z", "--", "."]


def ignored(path: Path) -> list[str]:
    """The untracked paths under ``path`` that git ignores, relative to it.

    The rules are git's own: ``.gitignore`` files, ``.git/info/exclude`` and
    ``core.excludesFile``. A directory ignored as a whole comes once, with a
    trailing ``/``; a tracked file is never listed, whatever the rules say.
    """
    return _names(run(_LIST_IGNORED, cwd=path))


def ignored_outside(root: Path, path: Path) -> list[str]:
    """What git would ignore under ``path``, a tree outside git rooted at ``root``.

    Same rules as :func:`ignored` -- the ``.gitignore`` files under ``root``
    and ``core.excludesFile`` -- read through an empty repository made in a
    temporary directory: nothing is ever written under ``root``.
    """
    with tempfile.TemporaryDirectory(prefix="scion-ignored-") as empty:
        run(["init", "-q", "--bare", empty])
        out = run(
            ["-c", "core.bare=false", "--git-dir", empty, "--work-tree", str(root),
             *_LIST_IGNORED],
            cwd=path,
        )
    return _names(out)


def _names(out: str) -> list[str]:
    return [name for name in out.split("\0") if name]
