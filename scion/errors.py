"""Exceptions raised by scion, each carrying the exit code it maps to.

Only :func:`scion.cli.main` turns these into a process exit code; nothing else
in the package calls ``sys.exit``.
"""

from __future__ import annotations


class ScionError(Exception):
    """A user error: unusable seed, no rootstock, conflicting graft..."""

    exit_code = 1


class GitError(ScionError):
    """A git invocation failed."""

    exit_code = 2
