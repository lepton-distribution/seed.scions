"""Every git invocation of the tool, as argument lists -- never a shell string."""

from __future__ import annotations

import contextlib
import logging
import subprocess
import tempfile
from pathlib import Path

from .errors import GitError

log = logging.getLogger(__name__)


def run(args: list[str], cwd: Path | None = None, input: str | None = None) -> str:
    """Run one git command and return its stdout; ``input`` goes to its stdin.

    Git's own output is captured rather than let through: it would interleave
    with the tool's logging, and on failure it is what the error message needs.
    """
    completed = _run(args, cwd, input)
    if completed.stderr:
        log.debug("%s", completed.stderr.rstrip())
    return completed.stdout


def run_verbatim(args: list[str], cwd: Path | None = None) -> tuple[str, str]:
    """Run one git command whose output is the point; return ``(stdout, stderr)``.

    On failure, both streams are carried by the :class:`GitError`.
    """
    completed = _run(args, cwd)
    return completed.stdout, completed.stderr


def _run(args: list[str], cwd: Path | None,
         input: str | None = None) -> subprocess.CompletedProcess:
    log.debug("git %s (cwd=%s)", " ".join(args), cwd)
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(cwd) if cwd else None,
            check=True,
            text=True,
            input=input,
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


@contextlib.contextmanager
def clone_parents(dest: Path):
    """Create the parents of a clone's ``dest``; undo that if the block fails.

    git removes the destination of a failed clone, never its parents. The
    directories missing before the call are created, and removed again --
    deepest first, by ``rmdir`` alone -- when the block raises: an empty
    directory made for this clone goes, a directory that existed before or that
    is no longer empty (a clone that succeeded) stays.
    """
    missing = []
    walker = dest.parent
    while not walker.exists():
        missing.append(walker)
        walker = walker.parent
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        yield
    except BaseException:
        removed = []
        for directory in missing:          # deepest first
            try:
                directory.rmdir()
            except OSError:
                break                      # not empty: its ancestors are not either
            removed.append(directory)
        if removed:
            log.debug("clonage en échec : répertoire(s) créé(s) pour %s retiré(s) : %s",
                      dest, ", ".join(str(d) for d in removed))
        raise


def clone(url: str, dest: Path, version: str = "master", single_branch: bool = False) -> None:
    """Clone ``url`` into ``dest`` and put it on ``version``.

    Without ``single_branch`` the whole repository is cloned and then checked
    out, which keeps the other branches available locally; with it, only the
    requested branch is fetched. The checkout is never skipped, ``master``
    included: the branch the origin's ``HEAD`` points to need not be the
    declared version, and a version the origin lacks is an error. A failed clone
    leaves no directory behind (:func:`clone_parents`); a clone whose checkout
    fails is kept.
    """
    with clone_parents(dest):
        if single_branch:
            run(["clone", "-b", version, "--single-branch", url, str(dest)])
            return
        run(["clone", url, str(dest)])
        run(["checkout", version], cwd=dest)


def clone_partial(url: str, dest: Path) -> None:
    """Clone ``url`` into ``dest`` without blobs nor checkout; the caller checks out.

    A failed clone leaves no directory behind (:func:`clone_parents`).
    """
    with clone_parents(dest):
        run(["clone", "--quiet", "--filter=blob:none", "--no-checkout", url, str(dest)])


def checkout_detached(dest: Path, commit_id: str) -> None:
    run(["checkout", "--quiet", "--detach", commit_id], cwd=dest)


def version() -> tuple[int, ...]:
    """The version of the git in the PATH: ``git version 2.50.1 (Apple Git-155)`` -> (2, 50, 1)."""
    words = run(["--version"]).split()
    parts: list[int] = []
    for piece in (words[2] if len(words) > 2 else "").split("."):
        if not piece.isdigit():
            break
        parts.append(int(piece))
    return tuple(parts)


def sparse_directories(dest: Path) -> list[str] | None:
    """The directories a partial extraction (cone mode) keeps, sorted.

    ``None`` when the whole tree is extracted. The files of the root, and those
    directly in the ancestors of these directories, are always extracted too.
    """
    try:
        enabled = run(["config", "--type=bool", "--get", "core.sparseCheckout"], cwd=dest)
    except GitError:
        return None
    if enabled.strip() != "true":
        return None
    return sorted(line for line in run(["sparse-checkout", "list"], cwd=dest).splitlines() if line)


def sparse_set(dest: Path, directories: list[str]) -> None:
    """Extract ``directories`` only (cone mode), fetching the blobs they need; none: the root."""
    run(["sparse-checkout", "set", "--cone", "--stdin"], cwd=dest,
        input="".join(f"{directory}\n" for directory in directories))


def is_full_sha(version: str) -> bool:
    """Whether ``version`` is a complete commit id: 40 hexadecimal characters."""
    return len(version) == 40 and all(c in "0123456789abcdefABCDEF" for c in version)


def has_commit(dest: Path, commit_id: str) -> bool:
    try:
        run(["cat-file", "-e", f"{commit_id}^{{commit}}"], cwd=dest)
    except GitError:
        return False
    return True


def fetch_origin(dest: Path) -> None:
    """Fetch every branch and tag of ``origin``."""
    run(["fetch", "--quiet", "--tags", "origin"], cwd=dest)


def ls_tree(dest: Path, rev: str) -> list[tuple[str, str]]:
    """``(mode, path)`` of every entry of ``rev``, recursively, paths exact."""
    found = []
    for record in run(["ls-tree", "-r", "-z", "--full-tree", rev], cwd=dest).split("\0"):
        if not record:
            continue
        meta, _, path = record.partition("\t")
        found.append((meta.split(" ", 1)[0], path))
    return found


def current_branch(dest: Path) -> str | None:
    """The branch checked out in ``dest``; ``None`` on a detached ``HEAD``."""
    return run(["branch", "--show-current"], cwd=dest).strip() or None


def is_branch(dest: Path, name: str) -> bool:
    """Whether ``name`` is a branch of ``dest``, local or of one of its remotes."""
    return bool(run(["for-each-ref", "--count=1", "--format=%(refname)",
                     f"refs/heads/{name}", f"refs/remotes/*/{name}"], cwd=dest).strip())


def tag_commit(dest: Path, name: str) -> str | None:
    """The commit the local tag ``name`` designates; ``None`` without such a tag."""
    try:
        return run(["rev-parse", "--verify", "--quiet", f"refs/tags/{name}^{{commit}}"],
                   cwd=dest).strip() or None
    except GitError:
        return None


def remote_tag_commit(dest: Path, name: str) -> str | None:
    """The commit the tag ``name`` designates in ``origin``; ``None`` if it has none."""
    found: dict[str, str] = {}
    out = run(["ls-remote", "--tags", "origin", f"refs/tags/{name}", f"refs/tags/{name}^{{}}"],
              cwd=dest)
    for line in out.splitlines():
        sha, _, ref = line.partition("\t")
        found[ref] = sha
    return found.get(f"refs/tags/{name}^{{}}") or found.get(f"refs/tags/{name}")


def is_ancestor(dest: Path, ancestor: str, descendant: str) -> bool:
    """Whether ``ancestor`` is an ancestor of ``descendant`` (or the same commit)."""
    try:
        run(["merge-base", "--is-ancestor", ancestor, descendant], cwd=dest)
    except GitError:
        return False
    return True


def refs(dest: Path, prefix: str) -> dict[str, tuple[str, str]]:
    """Branches and tags under ``prefix``: ``heads/x`` or ``tags/x`` -> (object, commit).

    The object is the tag object for an annotated tag; the commit is what it
    designates.
    """
    found: dict[str, tuple[str, str]] = {}
    out = run(["for-each-ref", "--format=%(objectname)%00%(*objectname)%00%(refname)",
               f"{prefix}heads", f"{prefix}tags"], cwd=dest)
    for line in out.splitlines():
        obj, peeled, name = line.split("\0")
        found[name[len(prefix):]] = (obj, peeled or obj)
    return found


def commit(dest: Path, rev: str = "HEAD") -> str:
    return run(["rev-parse", "--verify", f"{rev}^{{commit}}"], cwd=dest).strip()


def status_porcelain(dest: Path) -> str:
    return run(["status", "--porcelain"], cwd=dest)


def tracked_changes(dest: Path) -> str:
    """The changes to tracked files; untracked files are left out."""
    return run(["status", "--porcelain", "--untracked-files=no"], cwd=dest)


def upstream(dest: Path) -> str | None:
    """The upstream of the current branch, ``None`` without one."""
    try:
        return run(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
                   cwd=dest).strip() or None
    except GitError:
        return None


def fetch(dest: Path) -> None:
    run(["fetch", "--quiet"], cwd=dest)


def ahead_behind(dest: Path) -> tuple[int, int]:
    """Commits of ``HEAD`` missing from the upstream, and the other way round."""
    ahead, behind = run(
        ["rev-list", "--left-right", "--count", "HEAD...@{u}"], cwd=dest
    ).split()
    return int(ahead), int(behind)


def fast_forward(dest: Path) -> None:
    run(["merge", "--ff-only", "--quiet", "@{u}"], cwd=dest)


def head(dest: Path) -> str:
    return run(["rev-parse", "--short", "HEAD"], cwd=dest).strip()


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
