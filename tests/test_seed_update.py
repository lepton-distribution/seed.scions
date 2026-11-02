"""The seed's own repository moves with ``graft-update`` and ``seed-update``.

Only by fast-forward, from its upstream; a seed with local changes, or one that
diverged, stops the command before the trunk is touched. A seed without an
upstream, or outside git, is left as it is.
"""

from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

from support import FixtureCase, oracle, run

EXTRA = "extra/new.txt"
DELTA_CLONE = "depots/delta/extra/master"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def identify(repo: Path) -> None:
    git(repo, "config", "user.email", "fixture@example.invalid")
    git(repo, "config", "user.name", "scion fixture")


class SeedRepositoryCase(FixtureCase):
    """The fixture's seed, published in ``seed-origin`` and cloned in ``seed-local``."""

    def setUp(self):
        super().setUp()
        self.origin = self.base / "seed-origin"
        shutil.copytree(self.fx.seed, self.origin)
        git(self.origin, "init", "-q", "-b", "master")
        identify(self.origin)
        git(self.origin, "add", "-A")
        git(self.origin, "commit", "-qm", "seed")
        self.local = self.base / "seed-local"
        git(self.base, "clone", "-q", str(self.origin), str(self.local))
        identify(self.local)
        self.seed_add(self.local)
        code, _, err = self.graft()
        self.assertEqual(code, 0, err)

    def publish_new_scion(self) -> None:
        """One more scion, from a repository of its own, added to the published seed."""
        delta = self.fx.repos / "delta"
        (delta / "scion/extra").mkdir(parents=True)
        (delta / "scion" / EXTRA).write_text("new\n")
        git(delta, "init", "-q", "-b", "master")
        identify(delta)
        git(delta, "add", "-A")
        git(delta, "commit", "-qm", "delta")
        dot = self.origin / "scion/.scion"
        url = "file://localhost" + str(delta.resolve())
        with (dot / ".scion.sources.list").open("a") as handle:
            handle.write(f"delta\textra::new\tmaster\t{url}\n")
        with (dot / ".scion.ramifications").open("a") as handle:
            handle.write("delta\textra::new\tmaster\n")
        git(self.origin, "commit", "-qam", "extra::new")

    def commit_locally(self) -> None:
        sources = self.local / "scion/.scion/.scion.sources.list"
        sources.write_text(sources.read_text() + "# local\n")
        git(self.local, "commit", "-qam", "local")

    def head(self, repo: Path) -> str:
        return git(repo, "rev-parse", "HEAD")


class TestSeedAdvanced(SeedRepositoryCase):
    def test_graft_update_fast_forwards_the_seed_and_grafts_the_new_scion(self):
        self.publish_new_scion()
        code, _, err = run("graft-update", cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.head(self.local), self.head(self.origin))
        self.assertTrue((self.trunk / EXTRA).is_symlink())
        self.assertEqual(self.real_paths() - oracle(), {f"rootstock/{DELTA_CLONE}/scion/{EXTRA}"})

    def test_seed_update_fast_forwards_the_seed(self):
        self.publish_new_scion()
        code, _, err = run("seed-update", "--seed", str(self.local), cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.head(self.local), self.head(self.origin))
        self.assertTrue((self.rootstock / DELTA_CLONE / ".git").exists())

    def test_seed_ahead_of_its_upstream_is_kept(self):
        self.commit_locally()
        before = self.head(self.local)
        code, _, err = run("graft-update", cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.head(self.local), before)
        self.assertEqual(self.real_paths(), oracle())


class TestSeedRefused(SeedRepositoryCase):
    def assert_refused_and_trunk_intact(self, before_head: str, *words: str) -> None:
        expected = self.real_paths()
        code, _, err = run("graft-update", cwd=self.rootstock)
        self.assertNotEqual(code, 0)
        for word in words:
            self.assertIn(word, err)
        self.assertEqual(self.head(self.local), before_head)
        self.assertEqual(self.real_paths(), expected)
        self.assertFalse((self.trunk / EXTRA).exists())

    def test_seed_with_local_changes_is_refused(self):
        self.publish_new_scion()
        ramifications = self.local / "scion/.scion/.scion.ramifications"
        ramifications.write_text(ramifications.read_text() + "# en cours\n")
        self.assert_refused_and_trunk_intact(self.head(self.local), "modifications", str(self.local))

    def test_diverged_seed_is_refused(self):
        self.publish_new_scion()
        self.commit_locally()
        self.assert_refused_and_trunk_intact(self.head(self.local), "diverg", str(self.local))

    def test_untracked_file_in_the_seed_does_not_stop_it(self):
        self.publish_new_scion()
        (self.local / "notes.txt").write_text("brouillon\n")
        code, _, err = run("graft-update", cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.head(self.local), self.head(self.origin))


class TestSeedLeftAlone(FixtureCase):
    def test_seed_repository_without_upstream_is_left_as_it_is(self):
        seed = self.base / "seed-git"
        shutil.copytree(self.fx.seed, seed)
        git(seed, "init", "-q", "-b", "master")
        identify(seed)
        git(seed, "add", "-A")
        git(seed, "commit", "-qm", "seed")
        before = git(seed, "rev-parse", "HEAD")
        self.seed_add(seed)
        self.graft()
        code, _, err = run("graft-update", cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.assertEqual(git(seed, "rev-parse", "HEAD"), before)
        self.assertEqual(self.real_paths(), oracle())

    def test_seed_outside_git_is_left_as_it_is(self):
        self.seed_add()
        self.graft()
        code, _, err = run("graft-update", cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.real_paths(), oracle())


if __name__ == "__main__":
    unittest.main()
