"""Shared plumbing for the test modules.

The CLI is driven in-process so that exit codes and messages are checked
directly. Runs under ``python3 -m unittest discover -s tests`` as well as under
``pytest tests/``.
"""

from __future__ import annotations

import contextlib
import io
import logging
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DATA = Path(__file__).resolve().parent / "data"
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# scion logs at INFO; keep that out of the test report.
logging.basicConfig(level=logging.CRITICAL)

import make_fixture  # noqa: E402
from scion.cli import main  # noqa: E402


@contextlib.contextmanager
def chdir(path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def run(*argv: str, cwd=None) -> tuple[int, str, str]:
    """Invoke the CLI; returns ``(exit code, stdout, stderr)``."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.ExitStack() as stack:
        if cwd is not None:
            stack.enter_context(chdir(cwd))
        stack.enter_context(contextlib.redirect_stdout(out))
        stack.enter_context(contextlib.redirect_stderr(err))
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


def oracle() -> set[str]:
    """The reference trunk captured from scion.py 0.4.1.3-develop."""
    return {
        line
        for line in (DATA / "oracle-trunk.txt").read_text().splitlines()
        if line and not line.startswith("#")
    }


class FixtureCase(unittest.TestCase):
    """A fresh, network-free rootstock per test."""

    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="scion-test-"))
        self.addCleanup(self._cleanup)
        self.fx = make_fixture.build(self.base)
        self.rootstock = self.fx.rootstock
        self.trunk = self.fx.trunk

    def _cleanup(self) -> None:
        import shutil

        shutil.rmtree(self.base, ignore_errors=True)

    def seed_add(self, seed=None) -> None:
        code, _, err = run("seed-add", str(seed or self.fx.seed), cwd=self.rootstock)
        self.assertEqual(code, 0, err)

    def graft(self) -> tuple[int, str, str]:
        return run("graft", cwd=self.rootstock)

    def real_paths(self) -> set[str]:
        return make_fixture.real_paths(self.trunk, self.base)

    def dirty_clones(self) -> dict[str, str]:
        import subprocess

        dirty = {}
        for clone in self.fx.clones():
            status = subprocess.run(
                ["git", "status", "--porcelain"], cwd=clone,
                capture_output=True, text=True, check=True,
            ).stdout
            if status:
                dirty[str(clone.relative_to(self.base))] = status
        return dirty
