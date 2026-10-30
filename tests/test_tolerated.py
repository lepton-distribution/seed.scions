"""Regular files of the trunk the rootstock tolerates: no stop, gone on ungraft."""

from __future__ import annotations

import os
import subprocess
import unittest

from support import FixtureCase, run
from scion.rootstock import TOLERATED

BETA_CLONE = "depots/beta/tools/master"


class ToleratedCase(FixtureCase):
    def setUp(self):
        super().setUp()
        self.seed_add()
        code, _, err = self.graft()
        self.assertEqual(code, 0, err)
        (self.rootstock / TOLERATED).write_text("# système de fichiers\n\n.DS_Store\n._*\n")
        self.beta = self.rootstock / BETA_CLONE

    def drop(self, relative: str) -> None:
        (self.trunk / relative).write_text("finder\n")

    def left(self) -> list[str]:
        return sorted(str(p.relative_to(self.trunk)) for p in self.trunk.rglob("*")
                      if p.name != ".scion.grafted.list")


class TestUngraft(ToleratedCase):
    def test_tolerated_files_do_not_stop_it_and_go(self):
        self.drop("sys/.DS_Store")
        self.drop("tools/bin/._tool.sh")
        code, _, err = run("ungraft", cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.left(), [])

    def test_graft_regrafts_without_force(self):
        self.drop("sys/root/.DS_Store")
        code, _, err = self.graft()
        self.assertEqual(code, 0, err)
        self.assertFalse(os.path.lexists(self.trunk / "sys/root/.DS_Store"))
        self.assertTrue((self.trunk / "sys/root/src/kernel/core/kernel.c").is_symlink())

    def test_other_files_still_stop_it(self):
        self.drop("sys/.DS_Store")
        (self.trunk / "sys/notes.txt").write_text("mine\n")
        code, _, err = run("ungraft", cwd=self.rootstock)
        self.assertEqual(code, 1)
        self.assertIn("sys/notes.txt", err)
        self.assertNotIn(".DS_Store", err)
        self.assertIn(TOLERATED, err)
        self.assertTrue((self.trunk / "sys/.DS_Store").exists())

    def test_force_keeps_other_files_and_removes_tolerated_ones(self):
        self.drop("sys/.DS_Store")
        (self.trunk / "sys/notes.txt").write_text("mine\n")
        code, _, err = run("ungraft", "--force", cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.left(), ["sys", "sys/notes.txt"])

    def test_patterns_match_the_name_case_sensitively(self):
        self.drop("sys/.ds_store")
        code, _, err = run("ungraft", cwd=self.rootstock)
        self.assertEqual(code, 1)
        self.assertIn("sys/.ds_store", err)

    def test_without_the_file_nothing_is_tolerated(self):
        (self.rootstock / TOLERATED).unlink()
        self.drop("sys/.DS_Store")
        code, _, err = run("ungraft", cwd=self.rootstock)
        self.assertEqual(code, 1)
        self.assertIn("sys/.DS_Store", err)


class TestOneScion(ToleratedCase):
    def test_graft_scion_is_not_stopped(self):
        self.drop("sys/.DS_Store")
        code, _, err = run("graft", "--scion", "beta@tools::bin", cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.assertTrue((self.trunk / "sys/.DS_Store").exists())

    def test_pruned_directory_takes_its_tolerated_files(self):
        self.drop("tools/doc/deep/a/b/c/.DS_Store")
        self.drop("tools/doc/.DS_Store")
        subprocess.run(["git", "rm", "-rq", "scion/tools/doc"], cwd=self.beta, check=True)
        code, _, err = run("graft", "--scion", "beta@tools::bin", cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.assertFalse(os.path.lexists(self.trunk / "tools/doc"))

    def test_graft_remove_takes_its_tolerated_files(self):
        self.drop("tools/bin/.DS_Store")
        code, _, err = run("graft-remove", "beta@tools::bin", cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.assertFalse(os.path.lexists(self.trunk / "tools"))

    def test_directory_with_other_files_stays(self):
        self.drop("tools/bin/.DS_Store")
        (self.trunk / "tools/bin/notes.txt").write_text("mine\n")
        code, _, err = run("graft-remove", "--force", "beta@tools::bin", cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.assertTrue((self.trunk / "tools/bin/notes.txt").exists())
        self.assertTrue((self.trunk / "tools/bin/.DS_Store").exists())


class TestInstall(FixtureCase):
    def test_install_writes_a_tolerated_file_without_patterns(self):
        target = self.base / "fresh"
        target.mkdir()
        code, _, err = run("rootstock-install", cwd=target)
        self.assertEqual(code, 0, err)
        lines = (target / TOLERATED).read_text().splitlines()
        self.assertTrue(lines)
        self.assertTrue(all(line.startswith("#") for line in lines))


if __name__ == "__main__":
    unittest.main()
