"""A clone that is already there is checked before it is adopted.

``seed-clone`` reuses the clones it finds under ``depots/``. A clone it adopts
-- one whose scion is not grafted yet with that clone and that version, such as
a clone left by an earlier failure -- must be at its declared version: a branch
checked out, or the commit of a tag. Otherwise the command stops before
cloning anything, names every such clone with the command that puts it back,
and leaves the grafted list and the clone as they are. A clone that is already
grafted is not checked: work on another branch is regrafted as before, and
``seed-add``, ``seed-update`` and ``graft-update`` refuse it, as since 0.5.4.0.

``seed-add`` checks the same way the existing clone of a remote seed against
the version it is given. A projected scion is left to the graft, which refuses
a clone off its pinned commit (P-E1).

Every repository is local, reached through ``file://localhost``.
"""

from __future__ import annotations

import unittest
from pathlib import Path

import make_fixture
from support import run
from test_clone_checkout import CheckoutCase, git


class ExistingCloneCase(CheckoutCase):
    def foreign(self, version: str, url: str | None = None, at: Path | None = None) -> Path:
        """A clone made without ``-b``, on the origin's branch: what scion <= 0.6.3.1 left."""
        clone = at or self.target(version)
        clone.parent.mkdir(parents=True, exist_ok=True)
        git(clone.parent, "clone", "-q", url or self.plain, clone.name)
        return clone

    def seed_clone(self, expect: int = 0) -> str:
        code, _, err = run("seed-clone", "--seed", str(self.seed_dir), cwd=self.rootstock)
        self.assertEqual(code, expect, err)
        return err

    def head(self, clone: Path) -> tuple[str, str]:
        return git(clone, "branch", "--show-current"), git(clone, "rev-parse", "HEAD")

    def links(self) -> set[str]:
        trunk = self.rootstock / "trunk"
        return {str(p.relative_to(trunk)) for p in trunk.rglob("*") if p.is_symlink()}


# ==========================================================================
# seed-clone: an adopted clone off its version is refused
# ==========================================================================
class TestAdoptedClone(ExistingCloneCase):
    def test_branch_off_its_version_is_refused(self):
        self.ordinary("dev", self.plain)
        clone = self.foreign("dev")
        before = self.head(clone)
        err = self.seed_clone(expect=1)
        self.assertIn("branche « master », version déclarée « dev »", err)
        self.assertIn(f"git -C {clone.resolve()} switch dev", err)
        self.assertEqual(err.count("erreur :"), 1, err)
        self.assertNotIn("own plain ", self.grafted())
        self.assertEqual(self.head(clone), before)       # left in place

    def test_tag_off_its_commit_is_refused(self):
        self.ordinary("v1", self.plain)
        clone = self.foreign("v1")
        git(self.origin, "commit", "-q", "--allow-empty", "-m", "après v1")
        git(clone, "pull", "-q")
        err = self.seed_clone(expect=1)
        self.assertIn("tag « v1 »", err)
        self.assertIn("switch --detach v1", err)
        self.assertNotIn("own plain ", self.grafted())

    def test_nothing_is_grafted_after_the_refusal(self):
        """The path of a client: seed-scion-add, seed-clone, then graft --scion."""
        self.ordinary("dev", self.plain)
        self.foreign("dev")
        self.seed_clone(expect=1)
        run("graft", "--scion", "own@plain", cwd=self.rootstock)
        run("graft", cwd=self.rootstock)
        self.assertEqual(self.links(), set())

    def test_refused_before_anything_is_cloned(self):
        other = make_fixture.make_repo(self.base / "repos/other", {"scion/o.txt": "o\n"})
        self.declare(self.dot, [("own", "plain", "dev", self.plain),
                                ("own", "other", "master", other)], "")
        self.foreign("dev")
        self.seed_clone(expect=1)
        self.assertFalse((self.rootstock / "depots/own/other").exists())

    def test_every_faulty_clone_is_named(self):
        self.declare(self.dot, [("own", "plain", "dev", self.plain),
                                ("own", "plain2", "doc", self.plain)], "")
        dev = self.foreign("dev")
        doc = self.foreign("doc", at=self.rootstock / "depots/own/plain2/doc")
        err = self.seed_clone(expect=1)
        self.assertIn("2 clone(s)", err)
        self.assertIn(str(dev.resolve()), err)
        self.assertIn(str(doc.resolve()), err)

    def test_new_version_of_a_grafted_scion_is_adopted(self):
        """A grafted scion whose seed now declares another version takes a new clone."""
        self.ordinary("dev", self.plain)
        self.seed_add()
        self.ordinary("doc", self.plain)
        self.foreign("doc")
        err = self.seed_clone(expect=1)
        self.assertIn("version déclarée « doc »", err)
        self.assertIn("own plain dev ", self.grafted())

    def test_seed_add_refuses_it_too(self):
        """Unchanged since 0.5.4.0."""
        self.ordinary("dev", self.plain)
        self.foreign("dev")
        self.seed_add(expect=1)


class TestAdoptedCloneUnchanged(ExistingCloneCase):
    def test_adopted_clone_at_its_version_is_kept_as_it_is(self):
        self.ordinary("dev", self.plain)
        clone = self.foreign("dev")
        git(clone, "checkout", "-q", "dev")
        before = self.head(clone)
        self.seed_clone()
        self.assertEqual(self.head(clone), before)
        self.assertIn("own plain dev ", self.grafted())

    def test_adopted_tag_at_its_commit_is_kept(self):
        self.ordinary("v1", self.plain)
        clone = self.foreign("v1")
        git(clone, "checkout", "-q", "--detach", "v1")
        self.seed_clone()
        self.assertIn("own plain v1 ", self.grafted())

    def test_grafted_clone_on_a_work_branch_is_regrafted(self):
        """Work in a clone: another branch, then seed-clone and graft, as before."""
        self.ordinary("master", self.plain)
        self.seed_add()
        clone = self.target("master")
        git(clone, "checkout", "-q", "-b", "travail")
        self.seed_clone()
        code, _, err = run("graft", cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.assertEqual(git(clone, "branch", "--show-current"), "travail")

    def test_missing_clone_is_cloned(self):
        self.ordinary("dev", self.plain)
        self.seed_clone()
        self.assertEqual(git(self.target("dev"), "branch", "--show-current"), "dev")


# ==========================================================================
# seed-add: the existing clone of a remote seed
# ==========================================================================
class TestExistingRemoteSeed(ExistingCloneCase):
    def setUp(self) -> None:
        super().setUp()
        self.graine_repo = self.base / "repos/graine"
        self.graine = make_fixture.make_repo(self.graine_repo, {
            "scion/.scion/.scion.sources.list": f"own\tplain\tmaster\t{self.plain}\n",
            "scion/.scion/.scion.ramifications": "own\tplain\tmaster\n",
        })
        git(self.graine_repo, "tag", "t1")
        git(self.graine_repo, "checkout", "-q", "-b", "dev", "master")
        (self.graine_repo / "scion/.scion/.scion.sources.list").write_text(
            f"own\tplain\tdev\t{self.plain}\n")
        (self.graine_repo / "scion/.scion/.scion.ramifications").write_text("own\tplain\tdev\n")
        make_fixture.commit_all(self.graine_repo, "dev")
        git(self.graine_repo, "checkout", "-q", "master")
        self.local = self.rootstock / "depots/graine"

    def remote_seed_add(self, version: str, expect: int = 0) -> str:
        code, _, err = run("seed-add", "--version", version, self.graine, cwd=self.rootstock)
        self.assertEqual(code, expect, err)
        return err

    def test_seed_moved_off_its_branch_is_refused(self):
        self.remote_seed_add("dev")
        seed = self.local / "dev"
        git(seed, "checkout", "-q", "master")
        grafted = self.grafted()
        err = self.remote_seed_add("dev", expect=1)
        self.assertIn("branche « master », version demandée « dev »", err)
        self.assertIn(f"git -C {seed.resolve()} switch dev", err)
        self.assertEqual(err.count("erreur :"), 1, err)
        self.assertEqual(self.grafted(), grafted)
        self.assertFalse(self.target("master").exists())
        self.assertEqual(git(seed, "branch", "--show-current"), "master")

    def test_foreign_seed_clone_is_refused(self):
        seed = self.foreign("dev", self.graine, at=self.local / "dev")
        err = self.remote_seed_add("dev", expect=1)
        self.assertIn("version demandée « dev »", err)
        self.assertEqual(self.grafted().strip(), "")
        self.assertFalse((self.rootstock / "depots/own").exists())
        self.assertEqual(git(seed, "branch", "--show-current"), "master")

    def test_seed_tag_off_its_commit_is_refused(self):
        self.foreign("t1", self.graine, at=self.local / "t1")
        git(self.graine_repo, "commit", "-q", "--allow-empty", "-m", "après t1")
        git(self.local / "t1", "pull", "-q")
        err = self.remote_seed_add("t1", expect=1)
        self.assertIn("tag « t1 »", err)
        self.assertIn("switch --detach t1", err)

    def test_seed_at_its_branch_still_moves_forward(self):
        """Unchanged: an existing seed at its branch moves by fast-forward."""
        self.remote_seed_add("dev")
        seed = self.local / "dev"
        git(self.graine_repo, "checkout", "-q", "dev")
        git(self.graine_repo, "commit", "-q", "--allow-empty", "-m", "suite")
        git(self.graine_repo, "checkout", "-q", "master")
        self.remote_seed_add("dev")
        self.assertEqual(git(seed, "rev-parse", "HEAD"), git(self.graine_repo, "rev-parse", "dev"))

    def test_seed_given_as_a_path_is_not_checked(self):
        """A seed given as a path has no version: left as it is."""
        git(self.graine_repo, "checkout", "-q", "dev")
        code, _, err = run("seed-add", str(self.graine_repo), cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        git(self.graine_repo, "checkout", "-q", "master")


if __name__ == "__main__":
    unittest.main()
