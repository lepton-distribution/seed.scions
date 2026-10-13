"""Grafting or removing one scion while the rest of the trunk stays put."""

from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path

from support import FixtureCase, run
from scion.model import read_grafted

BETA_CLONE = "depots/beta/tools/master"


def git(clone: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t", *args],
        cwd=clone, check=True, capture_output=True,
    )


class GraftedCase(FixtureCase):
    def setUp(self):
        super().setUp()
        self.seed_add()
        code, _, err = self.graft()
        self.assertEqual(code, 0, err)
        self.beta = self.rootstock / BETA_CLONE

    def keys(self) -> list[str]:
        return list(read_grafted(self.trunk / ".scion.grafted.list"))

    def inode(self, relative: str) -> int:
        return os.lstat(self.trunk / relative).st_ino


class TestGraftOneScion(GraftedCase):
    def test_new_file_in_a_clone_is_grafted(self):
        (self.beta / "scion/tools/bin/new.sh").write_text("new\n")
        kernel = self.inode("sys/root/src/kernel/core/kernel.c")
        code, _, err = run("graft", "--scion", "beta@tools::bin", cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.assertTrue((self.trunk / "tools/bin/new.sh").is_symlink())
        self.assertEqual(self.inode("sys/root/src/kernel/core/kernel.c"), kernel)

    def test_same_tree_as_a_full_graft(self):
        (self.beta / "scion/tools/bin/new.sh").write_text("new\n")
        run("graft", "--scion", "beta@tools::bin", cwd=self.rootstock)
        partial = self.real_paths()
        code, _, err = self.graft()
        self.assertEqual(code, 0, err)
        self.assertEqual(self.real_paths(), partial)

    def test_deleted_files_and_directories_go(self):
        git(self.beta, "rm", "-rq", "scion/tools/doc")
        code, _, err = run("graft", "--scion", "beta@tools::bin", cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.assertFalse(os.path.lexists(self.trunk / "tools/doc"))
        self.assertTrue((self.trunk / "tools/bin/tool.sh").is_symlink())

    def test_conflict_restores_the_previous_links(self):
        (self.beta / "scion/sys/root/include").mkdir(parents=True)
        (self.beta / "scion/sys/root/include/kernel.h").write_text("dup\n")
        code, _, err = run("graft", "--scion", "beta@tools::bin", cwd=self.rootstock)
        self.assertEqual(code, 1)
        self.assertIn("alpha/core::kernel", err)
        self.assertIn("beta/tools::bin", err)
        self.assertTrue((self.trunk / "tools/bin/tool.sh").is_symlink())
        self.assertEqual(self.dirty_clones().keys(), {"rootstock/" + BETA_CLONE})

    def test_unknown_scion(self):
        code, _, err = run("graft", "--scion", "beta@nowhere", cwd=self.rootstock)
        self.assertEqual(code, 1)
        self.assertIn("beta@nowhere", err)

    def test_user_data_stops_it_unless_forced(self):
        (self.trunk / "sys/notes.txt").write_text("mine\n")
        code, _, err = run("graft", "--scion", "beta@tools::bin", cwd=self.rootstock)
        self.assertEqual(code, 1)
        self.assertIn("sys/notes.txt", err)
        code, _, err = run("graft", "--force", "--scion", "beta@tools::bin",
                           cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.assertTrue((self.trunk / "sys/notes.txt").exists())


class TestGraftRemove(GraftedCase):
    def test_only_its_leaves_go(self):
        kernel = self.inode("sys/root/src/kernel/core/kernel.c")
        code, _, err = run("graft-remove", "beta@tools::bin", cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.assertFalse(os.path.lexists(self.trunk / "tools"))
        self.assertNotIn("beta/tools::bin", self.keys())
        self.assertEqual(self.inode("sys/root/src/kernel/core/kernel.c"), kernel)
        self.assertTrue(self.beta.is_dir())
        self.assertEqual(self.dirty_clones(), {})

    def test_shared_directories_stay(self):
        code, _, err = run("graft-remove", "alpha@core::lib", cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.assertFalse(os.path.lexists(self.trunk / "sys/root/src/lib"))
        self.assertFalse(os.path.lexists(self.trunk / "sys/root/include/libc.h"))
        self.assertTrue((self.trunk / "sys/root/include/kernel.h").is_symlink())

    def test_empty_directories_of_the_scion_go(self):
        code, _, err = run("graft-remove", "local@building", cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.assertFalse(os.path.lexists(self.trunk / "building"))

    def test_regraft_after_removal_keeps_it_out(self):
        run("graft-remove", "beta@tools::bin", cwd=self.rootstock)
        code, _, err = self.graft()
        self.assertEqual(code, 0, err)
        self.assertFalse(os.path.lexists(self.trunk / "tools"))

    def test_unknown_scion(self):
        code, _, err = run("graft-remove", "beta@nowhere", cwd=self.rootstock)
        self.assertEqual(code, 1)
        self.assertIn("beta@nowhere", err)

    def test_user_data_stops_it_unless_forced(self):
        (self.trunk / "tools/notes.txt").write_text("mine\n")
        code, _, err = run("graft-remove", "beta@tools::bin", cwd=self.rootstock)
        self.assertEqual(code, 1)
        self.assertIn("beta/tools::bin", self.keys())
        code, _, err = run("graft-remove", "--force", "beta@tools::bin", cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.assertTrue((self.trunk / "tools/notes.txt").exists())
        self.assertFalse(os.path.lexists(self.trunk / "tools/bin"))


class TestPurge(GraftedCase):
    def assert_refused(self, key: str, reason: str) -> None:
        before = self.keys()
        code, _, err = run("graft-remove", "--purge", key, cwd=self.rootstock)
        self.assertEqual(code, 1, err)
        self.assertIn(reason, err)
        self.assertEqual(self.keys(), before)

    def test_purge_removes_the_clone(self):
        code, _, err = run("graft-remove", "--purge", "beta@tools::bin", cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.assertFalse((self.rootstock / "depots/beta").exists())
        self.assertTrue((self.rootstock / "depots/alpha").is_dir())

    def test_shared_clone_is_kept(self):
        self.assert_refused("alpha@core::lib", "partagé")
        self.assertTrue((self.trunk / "sys/root/src/lib/libc.c").is_symlink())

    def test_local_scion_is_not_purged(self):
        self.assert_refused("local@building", "n'a pas été cloné par scion")

    def test_dirty_clone_is_kept(self):
        (self.beta / "scion/tools/bin/tool.sh").write_text("changed\n")
        self.assert_refused("beta@tools::bin", "non commitées")
        self.assertTrue(self.beta.is_dir())

    def test_local_commit_is_kept(self):
        (self.beta / "scion/tools/bin/tool.sh").write_text("changed\n")
        git(self.beta, "commit", "-qam", "local work")
        self.assert_refused("beta@tools::bin", "absents de l'amont")
        self.assertTrue(self.beta.is_dir())


if __name__ == "__main__":
    unittest.main()
