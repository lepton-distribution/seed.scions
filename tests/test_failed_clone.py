"""A failed clone leaves no directory behind.

Before cloning, scion creates the parents of the destination; git removes the
destination of a failed clone, never its parents. The directories the call
created for the clone are removed again -- deepest first, empty ones only --
so that the rootstock is as it was. A directory that existed before the call,
empty or not, is never touched. A clone that succeeded and is kept on purpose
(a version the clone lacks, a mirror's work repository whose upstream cannot
be fetched) stays as it was.

Every repository is local, reached through ``file://localhost``; mirrors are
only ever synced with ``--dry-run``.
"""

from __future__ import annotations

import unittest
from pathlib import Path

import make_fixture
from support import run
from test_mirror import MirrorCase, url
from test_projection import ProjectionCase

PROJECTION = "tiers hal Inc/* scion/inc/\n"


def tree(root: Path) -> set[str]:
    """Every directory and file under ``depots/`` outside ``.git``, relative to ``root``."""
    found = set()
    for path in (root / "depots").rglob("*"):
        parts = path.relative_to(root).parts
        if ".git" in parts or any(part.endswith(".git") for part in parts[:-1]):
            continue
        found.add("/".join(parts))
    return found


class FailedCloneCase(ProjectionCase):
    """The rootstock, the seed and the third-party repository of :class:`ProjectionCase`."""

    def setUp(self) -> None:
        super().setUp()
        self.absent = self.url(self.base / "repos/absent.git")   # never created

    def ordinary(self, version: str, location: str) -> None:
        self.declare(self.dot, [("own", "plain", version, location)], "")

    def prepare(self, relative: str, witness: bool = True) -> None:
        """A directory there before the call; ``witness`` puts a file in it."""
        directory = self.rootstock / relative
        directory.mkdir(parents=True)
        if witness:
            (directory / "temoin").write_text("autre version\n")

    def failing_seed_add(self, *args: str, expect: int = 2) -> str:
        code, _, err = run("seed-add", *args, str(self.seed_dir), cwd=self.rootstock)
        self.assertEqual(code, expect, err)
        return err


# ==========================================================================
# ordinary scions and remote seeds (gitops.clone)
# ==========================================================================
class TestOrdinaryScion(FailedCloneCase):
    def test_new_shelf_leaves_nothing(self):
        self.ordinary("master", self.absent)
        self.failing_seed_add()
        self.assertEqual(tree(self.rootstock), set())

    def test_existing_shelf_keeps_only_what_was_there(self):
        self.prepare("depots/own/autre/master")
        before = tree(self.rootstock)
        self.ordinary("master", self.absent)
        self.failing_seed_add()
        self.assertEqual(tree(self.rootstock), before)

    def test_parent_holding_another_version_is_kept(self):
        self.prepare("depots/own/plain/v0")
        before = tree(self.rootstock)
        self.ordinary("master", self.absent)
        self.failing_seed_add()
        self.assertEqual(tree(self.rootstock), before)
        self.assertEqual((self.rootstock / "depots/own/plain/v0/temoin").read_text(),
                         "autre version\n")

    def test_empty_parent_already_there_is_kept(self):
        self.prepare("depots/own/plain", witness=False)
        self.ordinary("master", self.absent)
        self.failing_seed_add()
        self.assertEqual(tree(self.rootstock), {"depots/own", "depots/own/plain"})

    def test_single_branch_version_missing_upstream_leaves_nothing(self):
        plain = make_fixture.make_repo(self.base / "repos/plain", {"scion/f.txt": "f\n"})
        self.ordinary("nope", plain)
        self.failing_seed_add("--single-branch")
        self.assertEqual(tree(self.rootstock), set())

    def test_clone_whose_checkout_fails_is_kept(self):
        """Unchanged: the clone succeeded; the next pass refuses it (version check)."""
        plain = make_fixture.make_repo(self.base / "repos/plain", {"scion/f.txt": "f\n"})
        self.ordinary("nope", plain)
        self.failing_seed_add()
        self.assertTrue((self.rootstock / "depots/own/plain/nope/.git").is_dir())


class TestRemoteSeed(FailedCloneCase):
    def test_absent_remote_seed_leaves_nothing(self):
        code, _, err = run("seed-add", self.url(self.base / "repos/graine.git"),
                           cwd=self.rootstock)
        self.assertEqual(code, 2, err)
        self.assertEqual(tree(self.rootstock), set())


# ==========================================================================
# projected keys (gitops.clone_partial)
# ==========================================================================
class TestProjectedKey(FailedCloneCase):
    def test_new_shelf_leaves_nothing(self):
        self.seed(PROJECTION, location=self.absent)
        self.failing_seed_add()
        self.assertEqual(tree(self.rootstock), set())

    def test_existing_shelf_keeps_the_other_clone(self):
        self.ready(PROJECTION)
        before = tree(self.rootstock)
        self.seed(PROJECTION + "tiers hal2 Inc/* scion/inc2/\n",
                  extra=[("tiers", "hal2", "v1.0", self.absent)])
        self.failing_seed_add()
        self.assertEqual(tree(self.rootstock), before)

    def test_parent_holding_another_version_is_kept(self):
        self.ready(PROJECTION)
        before = tree(self.rootstock)
        self.seed(PROJECTION, version="v2.0", location=self.absent)
        self.failing_seed_add()
        self.assertEqual(tree(self.rootstock), before)

    def test_clone_lacking_the_version_is_kept(self):
        """Unchanged (P-V1): the clone succeeded and is left in place, as the message says."""
        self.seed(PROJECTION, version="v9.9")
        err = self.failing_seed_add(expect=1)
        self.assertIn("clone laissé en place", err)
        self.assertTrue((self.clone("v9.9") / ".git").exists())


# ==========================================================================
# message: one line under -v, nothing at the normal level
# ==========================================================================
class TestMessage(FailedCloneCase):
    def test_removal_is_logged_under_verbose_only(self):
        self.ordinary("master", self.absent)
        with self.assertLogs("scion.gitops", level="DEBUG") as logs:
            self.failing_seed_add()
        removed = [line for line in logs.output if "retiré" in line]
        self.assertEqual(len(removed), 1, logs.output)
        self.assertTrue(removed[0].startswith("DEBUG:"), removed)
        self.assertIn(str(self.rootstock / "depots/own"), removed[0])
        self.assertNotIn("erreur", removed[0])

    def test_nothing_logged_when_nothing_was_created(self):
        self.prepare("depots/own/plain", witness=False)
        self.ordinary("master", self.absent)
        with self.assertLogs("scion.gitops", level="DEBUG") as logs:
            self.failing_seed_add()
        self.assertFalse([line for line in logs.output if "retiré" in line], logs.output)


# ==========================================================================
# mirrors (mirror.sync_one), --dry-run only
# ==========================================================================
class TestMirrorWork(MirrorCase):
    def test_absent_mirror_leaves_nothing(self):
        self.declare((self.base / "mirrors/absent.git", self.upstream))
        self.sync("--dry-run", expect=1)
        self.assertEqual(tree(self.rootstock), set())

    def test_ancestors_made_for_another_mirror_are_kept(self):
        self.declare((self.mirror, self.base / "repos/absent"))
        self.sync("--dry-run", expect=1)
        before = tree(self.rootstock)
        self.declare((self.mirror, self.base / "repos/absent"),
                     (self.base / "mirrors/absent.git", self.upstream))
        self.sync("--dry-run", expect=1)
        self.assertEqual(tree(self.rootstock), before)

    def test_work_repository_kept_when_upstream_unreachable(self):
        """Unchanged (M-C6): the work repository was cloned; it serves the next pass."""
        self.declare((self.mirror, self.base / "repos/absent"))
        self.sync("--dry-run", expect=1)
        self.assertTrue((self.work() / "config").is_file())


if __name__ == "__main__":
    unittest.main()
