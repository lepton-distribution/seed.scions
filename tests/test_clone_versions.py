"""Clones are brought to their declared version, and a failed regraft keeps the trunk.

``graft-update``, ``seed-update`` and ``seed-add`` check every existing clone
before anything moves: a clone off its declared version (another branch, a
detached ``HEAD``), diverged from its upstream, without one, or behind it with
changes to tracked files stops the command; the trunk and the clones are left
as they are. A clone moves by fast-forward only, never by ``git pull``. A
version that is a tag is checked, not pulled.

``graft`` and ``graft-update`` put back the trunk they found -- links,
directories and grafted list -- when the regraft fails.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import unittest
from pathlib import Path

from support import FixtureCase, run

NEW = "tools/bin/new.sh"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def identify(repo: Path) -> None:
    git(repo, "config", "user.email", "fixture@example.invalid")
    git(repo, "config", "user.name", "scion fixture")


def trunk_state(trunk: Path) -> tuple[frozenset, frozenset]:
    """Every link with its target, and every directory, of the trunk."""
    links, dirs = set(), set()
    for dirpath, dirnames, filenames in os.walk(trunk, followlinks=False):
        for name in dirnames + filenames:
            path = Path(dirpath) / name
            relative = str(path.relative_to(trunk))
            if path.is_symlink():
                links.add((relative, os.readlink(path)))
            elif path.is_dir():
                dirs.add(relative)
    return frozenset(links), frozenset(dirs)


class CloneCase(FixtureCase):
    """The fixture, grafted; ``beta`` is the upstream of the clone under test."""

    def setUp(self):
        super().setUp()
        self.beta = self.fx.repos / "beta"
        self.prepare_seed()
        self.seed_add()
        code, _, err = self.graft()
        self.assertEqual(code, 0, err)
        self.clone = self.clone_of("beta")
        identify(self.clone)
        self.before = trunk_state(self.trunk)
        self.grafted = (self.trunk / ".scion.grafted.list").read_text()

    def prepare_seed(self) -> None:
        """Hook for a different declaration of ``beta``."""

    def clone_of(self, shelf: str) -> Path:
        return next(c for c in self.fx.clones()
                    if c.relative_to(self.fx.depots).parts[0] == shelf).resolve()

    def advance_upstream(self, name: str = NEW, text: str = "new\n") -> None:
        path = self.beta / "scion" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        git(self.beta, "add", "-A")
        git(self.beta, "commit", "-qm", "upstream")

    def commit_in_clone(self, name: str = "tools/bin/local.sh") -> str:
        (self.clone / "scion" / name).write_text("local\n")
        git(self.clone, "add", "-A")
        git(self.clone, "commit", "-qm", "local")
        return git(self.clone, "rev-parse", "HEAD")

    def head(self) -> str:
        return git(self.clone, "rev-parse", "HEAD")

    def branch(self) -> str:
        return git(self.clone, "branch", "--show-current")

    def assert_trunk_intact(self) -> None:
        self.assertEqual(trunk_state(self.trunk), self.before)
        self.assertEqual((self.trunk / ".scion.grafted.list").read_text(), self.grafted)

    def assert_refused(self, *words: str, command: tuple[str, ...] = ("graft-update",),
                       code: int = 1) -> str:
        head, branch = self.head(), self.branch()
        got, _, err = run(*command, cwd=self.rootstock)
        self.assertEqual(got, code, err)
        for word in words:
            self.assertIn(word, err)
        self.assertEqual(self.head(), head)
        self.assertEqual(self.branch(), branch)
        self.assert_trunk_intact()
        return err


class TestCloneOffItsVersion(CloneCase):
    def test_other_local_branch_is_refused(self):
        git(self.clone, "switch", "-qc", "old")
        self.advance_upstream()
        self.assert_refused(str(self.clone), "« old »", "« master »",
                            f"git -C {self.clone} switch master")

    def test_other_published_branch_behind_is_refused(self):
        """E-1: the clone was pulled on its own branch, silently."""
        git(self.beta, "branch", "old")
        self.advance_upstream()
        git(self.clone, "fetch", "-q")
        git(self.clone, "switch", "-q", "old")
        self.assert_refused(str(self.clone), "« old »")
        self.assertFalse((self.trunk / NEW).exists())

    def test_branch_with_unpublished_commits_is_never_moved(self):
        git(self.clone, "switch", "-qc", "work")
        mine = self.commit_in_clone()
        self.advance_upstream()
        self.assert_refused("« work »")
        self.assertEqual(git(self.clone, "rev-parse", "work"), mine)

    def test_detached_head_is_refused(self):
        git(self.clone, "switch", "-q", "--detach", "HEAD")
        self.advance_upstream()
        self.assert_refused(str(self.clone), "détaché")

    def test_seed_update_refuses_too(self):
        git(self.clone, "switch", "-qc", "old")
        self.advance_upstream()
        self.assert_refused("« old »", command=("seed-update", "--seed", str(self.fx.seed)))

    def test_seed_add_refuses_too(self):
        git(self.clone, "switch", "-qc", "old")
        self.advance_upstream()
        self.assert_refused("« old »", command=("seed-add", str(self.fx.seed)))

    def test_every_faulty_clone_is_listed(self):
        alpha = self.clone_of("alpha")
        git(self.clone, "switch", "-qc", "old")
        git(alpha, "switch", "-qc", "other")
        err = self.assert_refused("2 clone(s)")
        self.assertIn(str(alpha), err)
        self.assertIn(str(self.clone), err)


class TestCloneAtItsVersion(CloneCase):
    def test_behind_moves_by_fast_forward(self):
        self.advance_upstream()
        code, _, err = run("graft-update", cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.head(), git(self.beta, "rev-parse", "HEAD"))
        self.assertEqual(git(self.clone, "rev-list", "--merges", "--count", "HEAD"), "0")
        self.assertTrue((self.trunk / NEW).is_symlink())

    def test_seed_update_moves_the_clone(self):
        self.advance_upstream()
        code, _, err = run("seed-update", "--seed", str(self.fx.seed), cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.head(), git(self.beta, "rev-parse", "HEAD"))

    def test_diverged_is_refused(self):
        mine = self.commit_in_clone()
        self.advance_upstream()
        self.assert_refused(str(self.clone), "diverg")
        self.assertEqual(self.head(), mine)

    def test_ahead_only_is_left_as_it_is(self):
        mine = self.commit_in_clone()
        code, _, err = run("graft-update", cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.head(), mine)

    def test_behind_with_tracked_changes_is_refused(self):
        (self.clone / "scion/tools/bin/tool.sh").write_text("changed\n")
        self.advance_upstream()
        self.assert_refused(str(self.clone), "modifications")
        self.assertEqual((self.clone / "scion/tools/bin/tool.sh").read_text(), "changed\n")

    def test_behind_with_conflicting_changes_is_refused(self):
        (self.clone / "scion/tools/bin/tool.sh").write_text("changed\n")
        (self.beta / "scion/tools/bin/tool.sh").write_text("upstream\n")
        git(self.beta, "commit", "-qam", "upstream")
        self.assert_refused(str(self.clone), "modifications")

    def test_tracked_changes_up_to_date_are_left(self):
        (self.clone / "scion/tools/bin/tool.sh").write_text("changed\n")
        code, _, err = run("graft-update", cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.assertEqual((self.clone / "scion/tools/bin/tool.sh").read_text(), "changed\n")

    def test_branch_without_upstream_is_refused(self):
        git(self.clone, "branch", "--unset-upstream")
        self.assert_refused(str(self.clone), "amont")

    def test_unreachable_upstream_keeps_the_trunk(self):
        shutil.move(str(self.beta), str(self.beta) + ".away")
        self.assert_refused(code=2)


class TestTagVersion(CloneCase):
    """``beta`` declared by an annotated tag: the clone sits on a detached ``HEAD``."""

    def prepare_seed(self) -> None:
        git(self.beta, "tag", "-a", "v1", "-m", "v1")
        dot = self.fx.seed / "scion/.scion"
        for name in (".scion.sources.list", ".scion.ramifications"):
            path = dot / name
            path.write_text("\n".join(
                line.replace("master", "v1") if line.startswith("beta") else line
                for line in path.read_text().splitlines()) + "\n")

    def test_tag_is_not_pulled(self):
        self.advance_upstream()
        code, _, err = run("graft-update", cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.head(), git(self.beta, "rev-parse", "v1^{commit}"))
        self.assert_trunk_intact()

    def test_head_off_the_tag_is_refused(self):
        git(self.clone, "switch", "-q", "--detach", "HEAD")
        self.commit_in_clone()
        self.assert_refused(str(self.clone), "« v1 »")

    def test_tag_moved_upstream_is_refused(self):
        self.advance_upstream()
        git(self.beta, "tag", "-f", "-a", "v1", "-m", "v1 moved")
        self.assert_refused(str(self.clone), "« v1 »", "amont")


class TestFailedRegraftKeepsTheTrunk(CloneCase):
    def test_conflict_brought_by_the_upstream(self):
        # alpha's core::kernel already provides sys/root/include/kernel.h
        self.advance_upstream("sys/root/include/kernel.h", "/* duplicate */\n")
        code, _, err = run("graft-update", cwd=self.rootstock)
        self.assertEqual(code, 1, err)
        self.assertIn("conflit", err)
        self.assertIn("rétabli", err)
        self.assert_trunk_intact()

    def test_graft_conflict_keeps_the_trunk(self):
        self.seed_add(self.fx.seed_conflict)
        code, _, err = self.graft()
        self.assertEqual(code, 1, err)
        self.assertIn("rétabli", err)
        self.assertEqual(trunk_state(self.trunk), self.before)

    def test_restored_trunk_regrafts_once_fixed(self):
        self.seed_add(self.fx.seed_conflict)
        self.graft()
        code, _, err = run("graft-remove", "gamma@x::dup", cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        code, _, err = self.graft()
        self.assertEqual(code, 0, err)
        self.assertEqual(trunk_state(self.trunk), self.before)


if __name__ == "__main__":
    unittest.main()
