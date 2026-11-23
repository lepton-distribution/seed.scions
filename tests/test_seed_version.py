"""A cloned seed off its version stops ``seed-update`` and ``graft-update``.

``seed-add URL --version V`` clones a remote seed in ``depots/<name>/<V>``,
``<name>`` being the last part of the URL. ``seed-update`` and ``graft-update``
move a seed by fast-forward from its upstream. A seed cloned this way must be
at ``V`` first -- the branch checked out, or the commit of the tag --, or the
command stops before anything has changed, names the seed and the command that
puts it back. Such a seed is recognized by its place alone: its repository is
``depots/<last part of its origin URL>/<V>``. A seed given as a path, or one
without an origin, has no version and moves as before.

Every repository is local, reached through ``file://localhost``.
"""

from __future__ import annotations

import unittest
from pathlib import Path

import make_fixture
from support import run
from test_existing_clone import ExistingCloneCase
from test_clone_checkout import git


class RemoteSeedCase(ExistingCloneCase):
    """Remote seed ``graine``: master names own/plain master, dev and f/x own/plain dev."""

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
        git(self.graine_repo, "tag", "-a", "t1", "-m", "t1")
        git(self.graine_repo, "branch", "f/x")
        git(self.graine_repo, "checkout", "-q", "master")
        self.local = self.rootstock / "depots/graine"

    def remote_seed_add(self, version: str) -> Path:
        code, _, err = run("seed-add", "--version", version, self.graine, cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        return self.local / version

    def advance(self, branch: str) -> str:
        """One more commit on ``branch`` of the seed's origin; returns it."""
        git(self.graine_repo, "checkout", "-q", branch)
        git(self.graine_repo, "commit", "-q", "--allow-empty", "-m", f"suite de {branch}")
        git(self.graine_repo, "checkout", "-q", "master")
        return git(self.graine_repo, "rev-parse", branch)

    def seed_update(self, seed: Path, expect: int = 0) -> str:
        code, _, err = run("seed-update", "--seed", str(seed), cwd=self.rootstock)
        self.assertEqual(code, expect, err)
        return err

    def graft_update(self, expect: int = 0) -> str:
        code, _, err = run("graft-update", cwd=self.rootstock)
        self.assertEqual(code, expect, err)
        return err


class TestSeedOffItsVersion(RemoteSeedCase):
    def assert_nothing_changed(self, seed: Path, head: tuple[str, str], grafted: str,
                               links: set[str]) -> None:
        self.assertEqual(self.head(seed), head)
        self.assertEqual(self.grafted(), grafted)
        self.assertEqual(self.links(), links)
        self.assertFalse(self.target("master").exists())

    def test_seed_update_refuses_a_seed_moved_off_its_branch(self):
        seed = self.remote_seed_add("dev")
        git(seed, "checkout", "-q", "master")
        self.advance("master")
        head, grafted, links = self.head(seed), self.grafted(), self.links()
        err = self.seed_update(seed, expect=1)
        self.assertIn("graine hors de la version demandée", err)
        self.assertIn("branche « master », version demandée « dev »", err)
        self.assertIn(f"git -C {seed.resolve()} switch dev", err)
        self.assertIn("rien n'a été modifié", err)
        self.assertEqual(err.count("erreur :"), 1, err)
        self.assert_nothing_changed(seed, head, grafted, links)

    def test_graft_update_refuses_it_too(self):
        seed = self.remote_seed_add("dev")
        self.graft()
        git(seed, "checkout", "-q", "master")
        self.advance("master")
        head, grafted, links = self.head(seed), self.grafted(), self.links()
        self.assertTrue(links)
        err = self.graft_update(expect=1)
        self.assertIn("version demandée « dev »", err)
        self.assert_nothing_changed(seed, head, grafted, links)

    def test_detached_seed_is_refused(self):
        """A detached seed has no upstream, and was left as it is: it is refused now."""
        seed = self.remote_seed_add("dev")
        git(seed, "checkout", "-q", "--detach", "origin/master")
        err = self.seed_update(seed, expect=1)
        self.assertIn("HEAD détaché", err)
        self.assertIn("version demandée « dev »", err)

    def test_tag_seed_moved_to_a_branch_is_refused(self):
        seed = self.remote_seed_add("t1")
        self.advance("dev")
        git(seed, "fetch", "-q")
        git(seed, "checkout", "-q", "dev")
        head = self.head(seed)
        err = self.seed_update(seed, expect=1)
        self.assertIn("tag « t1 »", err)
        self.assertIn(f"git -C {seed.resolve()} switch --detach t1", err)
        self.assertEqual(self.head(seed), head)

    def test_tag_seed_on_a_branch_at_the_tag_is_not_moved(self):
        """A tag is checked, never pulled: on a branch still at the tag, it stays there."""
        seed = self.remote_seed_add("t1")
        git(seed, "checkout", "-q", "dev")
        head = self.head(seed)
        self.advance("dev")
        self.seed_update(seed)
        self.assertEqual(self.head(seed), head)

    def test_version_with_a_slash_is_read_from_the_whole_path(self):
        seed = self.remote_seed_add("f/x")
        git(seed, "checkout", "-q", "master")
        err = self.seed_update(seed, expect=1)
        self.assertIn("version demandée « f/x »", err)


class TestSeedVersionUnchanged(RemoteSeedCase):
    def test_seed_at_its_branch_moves_forward_with_seed_update(self):
        seed = self.remote_seed_add("dev")
        ahead = self.advance("dev")
        self.seed_update(seed)
        self.assertEqual(self.head(seed), ("dev", ahead))

    def test_seed_at_its_branch_moves_forward_with_graft_update(self):
        seed = self.remote_seed_add("dev")
        self.graft()
        ahead = self.advance("dev")
        self.graft_update()
        self.assertEqual(self.head(seed), ("dev", ahead))

    def test_seed_at_its_tag_is_left_as_it_is(self):
        seed = self.remote_seed_add("t1")
        head = self.head(seed)
        self.advance("dev")
        self.seed_update(seed)
        self.assertEqual(self.head(seed), head)

    def test_seed_given_as_a_path_is_not_checked(self):
        mine = self.base / "graine-locale"
        git(self.base, "clone", "-q", "-b", "dev", self.graine, mine.name)
        code, _, err = run("seed-add", str(mine), cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        git(mine, "checkout", "-q", "master")
        ahead = self.advance("master")
        self.seed_update(mine)
        self.assertEqual(self.head(mine), ("master", ahead))

    def test_seed_placed_under_depots_by_hand_is_not_checked(self):
        """Its directory is not named after its origin: it was given as a path."""
        by_hand = self.rootstock / "depots/manuel/travail"
        by_hand.parent.mkdir(parents=True)
        git(by_hand.parent, "clone", "-q", "-b", "dev", self.graine, by_hand.name)
        code, _, err = run("seed-add", str(by_hand), cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        ahead = self.advance("dev")
        self.seed_update(by_hand)
        self.assertEqual(self.head(by_hand), ("dev", ahead))

    def test_local_seed_without_origin_is_not_checked(self):
        projet = self.rootstock / "depots/projets/p1"
        make_fixture.make_repo(projet, {
            "scion/.scion/.scion.sources.list": f"own\tplain\tmaster\t{self.plain}\n",
            "scion/.scion/.scion.ramifications": "own\tplain\tmaster\n",
        })
        code, _, err = run("seed-add", str(projet), cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.seed_update(projet)


if __name__ == "__main__":
    unittest.main()
