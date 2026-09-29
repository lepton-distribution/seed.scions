"""Every git invocation of the tool, as argument lists -- never a shell string."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from .errors import GitError

log = logging.getLogger(__name__)


def run(args: list[str], cwd: Path | None = None) -> str:
    """Run one git command and return its stdout.

    Git's own output is captured rather than let through: it would interleave
    with the tool's logging, and on failure it is what the error message needs.
    """
    log.debug("git %s (cwd=%s)", " ".join(args), cwd)
    try:
        completed = subprocess.run(
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
            + (f" : {detail[-1]}" if detail else "")
        ) from exc
    if completed.stderr:
        log.debug("%s", completed.stderr.rstrip())
    return completed.stdout


def clone(url: str, dest: Path, version: str = "master", single_branch: bool = False) -> None:
    """Clone ``url`` into ``dest`` and put it on ``version``.

    Without ``single_branch`` the whole repository is cloned and then checked
    out, which keeps the other branches available locally; with it, only the
    requested branch is fetched.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    if single_branch:
        run(["clone", "-b", version, "--single-branch", url, str(dest)])
        return
    run(["clone", url, str(dest)])
    if version != "master":
        run(["checkout", version], cwd=dest)


def pull(dest: Path) -> None:
    run(["pull"], cwd=dest)


def status_porcelain(dest: Path) -> str:
    return run(["status", "--porcelain"], cwd=dest)
