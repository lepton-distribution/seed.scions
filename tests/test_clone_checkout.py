"""A clone is made at its declared version, or not at all.

Without ``--single-branch``, an ordinary scion and a remote seed are cloned with
every branch and put on their version by git itself (``git clone -b``). A
version that the origin lacks as a branch or a tag -- absent, a path of the
repository, a commit, an empty origin -- is refused before any work tree is
written, and leaves no clone behind: the next pass clones again and fails the
same way, so a clone left on the origin's branch can never be grafted. A
branch named like a directory of the repository is a branch. A version that
exists is checked out as before: a branch tracking its upstream, a tag on a
detached ``HEAD``, the other branches still fetched.

Every repository is local, reached through ``file://localhost``.
"""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

import make_fixture
from support import run
from test_failed_clone import FailedCloneCase, tree


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True,
                          text=True).stdout.strip()


class CheckoutCase(FailedCloneCase):
    """An origin ``plain`` on ``master``, with a branch ``dev``, a tag ``v1``, a directory ``doc/``
    and a branch ``doc``."""

    def setUp(self) -> None:
        super().setUp()
        self.origin = self.base / "repos/plain"
        self.plain = make_fixture.make_repo(self.origin, {"scion/f.txt": "f\n", "doc/d.txt": "d\n"})
        git(self.origin, "tag", "v1")
        for branch in ("dev", "doc"):
            git(self.origin, "checkout", "-q", "-b", branch, "master")
            (self.origin / f"scion/{branch}.txt").write_text(f"{branch}\n")
            make_fixture.commit_all(self.origin, branch)
        git(self.origin, "checkout", "-q", "master")

    def target(self, version: str) -> Path:
        return self.rootstock / "depots/own/plain" / version

    def seed_add(self, *args: str, expect: int = 0) -> str:
        code, _, err = run("seed-add", *args, str(self.seed_dir), cwd=self.rootstock)
        self.assertEqual(code, expect, err)
        return err

    def grafted(self) -> str:
        listed = self.rootstock / "trunk/.scion.grafted.list"
        return listed.read_text() if listed.exists() else ""


# ==========================================================================
# ordinary scion (graft._fetch -> gitops.clone)
# ==========================================================================
class TestOrdinaryVersionMissing(CheckoutCase):
    def test_missing_version_leaves_no_clone(self):
        self.ordinary("nope", self.plain)
        err = self.seed_add(expect=2)
        self.assertEqual(tree(self.rootstock), set())
        self.assertEqual(err.count("erreur :"), 1, err)
        self.assertIn("nope", err)

    def test_next_pass_fails_the_same_way(self):
        self.ordinary("nope", self.plain)
        first = self.seed_add(expect=2)
        second = self.seed_add(expect=2)
        self.assertEqual(second, first)
        self.assertEqual(tree(self.rootstock), set())

    def test_seed_clone_after_a_failure_lists_nothing(self):
        """The path lepton takes (seed-scion-add, seed-clone, graft --scion)."""
        self.ordinary("nope", self.plain)
        self.seed_add(expect=2)
        code, _, err = run("seed-clone", "--seed", str(self.seed_dir), cwd=self.rootstock)
        self.assertEqual(code, 2, err)
        self.assertNotIn("own plain ", self.grafted())
        self.assertEqual(tree(self.rootstock), set())

    def test_version_that_is_only_a_path_is_refused(self):
        self.ordinary("scion", self.plain)
        self.seed_add(expect=2)
        self.assertEqual(tree(self.rootstock), set())
        self.assertNotIn("own plain ", self.grafted())

    def test_full_commit_is_refused_at_once(self):
        """The version check knows branches and tags only; the clone now agrees."""
        self.ordinary(git(self.origin, "rev-parse", "master"), self.plain)
        self.seed_add(expect=2)
        self.assertEqual(tree(self.rootstock), set())

    def test_empty_origin_leaves_no_clone(self):
        empty = self.base / "repos/vide.git"
        empty.mkdir(parents=True)
        git(empty, "init", "-q", "--bare")
        self.ordinary("master", self.url(empty))
        self.seed_add(expect=2)
        self.assertEqual(tree(self.rootstock), set())


class TestOrdinaryVersionPresent(CheckoutCase):
    def test_branch_named_like_a_directory_is_cloned(self):
        self.ordinary("doc", self.plain)
        self.seed_add()
        clone = self.target("doc")
        self.assertEqual(git(clone, "branch", "--show-current"), "doc")
        self.assertEqual(git(clone, "rev-parse", "--abbrev-ref", "@{u}"), "origin/doc")
        self.assertTrue((clone / "scion/doc.txt").is_file())

    def test_branch_other_than_the_origin_head(self):
        """Unchanged: the declared branch, tracking its upstream, the others still fetched."""
        self.ordinary("dev", self.plain)
        self.seed_add()
        clone = self.target("dev")
        self.assertEqual(git(clone, "branch", "--show-current"), "dev")
        self.assertEqual(git(clone, "rev-parse", "--abbrev-ref", "@{u}"), "origin/dev")
        self.assertEqual(git(clone, "rev-parse", "HEAD"), git(self.origin, "rev-parse", "dev"))
        remotes = git(clone, "branch", "-r").split()
        self.assertIn("origin/master", remotes)
        self.assertIn("origin/doc", remotes)

    def test_master(self):
        """Unchanged: master is checked out even when it is the origin's HEAD."""
        self.ordinary("master", self.plain)
        self.seed_add()
        clone = self.target("master")
        self.assertEqual(git(clone, "branch", "--show-current"), "master")
        self.assertEqual(git(clone, "rev-parse", "--abbrev-ref", "@{u}"), "origin/master")

    def test_tag_is_a_detached_head(self):
        """Unchanged: a tag is checked out on a detached HEAD, and the next pass accepts it."""
        self.ordinary("v1", self.plain)
        self.seed_add()
        clone = self.target("v1")
        self.assertEqual(git(clone, "branch", "--show-current"), "")
        self.assertEqual(git(clone, "rev-parse", "HEAD"), git(self.origin, "rev-parse", "v1"))
        self.seed_add()

    def test_present_version_next_pass_accepts_the_clone(self):
        self.ordinary("dev", self.plain)
        self.seed_add()
        self.seed_add()
        self.assertIn("own plain dev ", self.grafted())


# ==========================================================================
# remote seed (cli._clone_seed -> gitops.clone)
# ==========================================================================
class TestRemoteSeedVersion(CheckoutCase):
    def setUp(self) -> None:
        super().setUp()
        self.graine_repo = self.base / "repos/graine"
        self.graine = make_fixture.make_repo(self.graine_repo, {
            "scion/.scion/.scion.sources.list": f"own\tplain\tmaster\t{self.plain}\n",
            "scion/.scion/.scion.ramifications": "own\tplain\tmaster\n",
        })
        git(self.graine_repo, "checkout", "-q", "-b", "dev", "master")
        (self.graine_repo / "scion/.scion/.scion.sources.list").write_text(
            f"own\tplain\tdev\t{self.plain}\n")
        (self.graine_repo / "scion/.scion/.scion.ramifications").write_text("own\tplain\tdev\n")
        make_fixture.commit_all(self.graine_repo, "dev")
        git(self.graine_repo, "checkout", "-q", "master")

    def remote_seed_add(self, version: str, expect: int = 0) -> str:
        code, _, err = run("seed-add", "--version", version, self.graine, cwd=self.rootstock)
        self.assertEqual(code, expect, err)
        return err

    def test_missing_seed_version_leaves_no_clone(self):
        self.remote_seed_add("nope", expect=2)
        self.assertEqual(tree(self.rootstock), set())

    def test_next_pass_does_not_read_the_origin_branch(self):
        self.remote_seed_add("nope", expect=2)
        self.remote_seed_add("nope", expect=2)
        self.assertEqual(tree(self.rootstock), set())
        self.assertEqual(self.grafted().strip(), "")

    def test_seed_version_that_is_only_a_path_is_refused(self):
        self.remote_seed_add("scion", expect=2)
        self.assertEqual(tree(self.rootstock), set())

    def test_seed_branch_is_read(self):
        """Unchanged: the seed is read at its declared branch."""
        self.remote_seed_add("dev")
        seed = self.rootstock / "depots/graine/dev"
        self.assertEqual(git(seed, "branch", "--show-current"), "dev")
        self.assertIn("own plain dev ", self.grafted())


if __name__ == "__main__":
    unittest.main()
