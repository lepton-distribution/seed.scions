"""Files git ignores are never grafted; everything else still is.

A scion outside git follows git's rules too: those of its own ``.gitignore``
files and of the global configuration, read through an empty repository kept
out of the source.
"""

from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from support import FixtureCase, oracle, run

ALPHA_CLONE = "depots/alpha/core/master"
BETA_CLONE = "depots/beta/tools/master"
BUILDING = "depots/generation/building"


class IgnoredCase(FixtureCase):
    """Git's global configuration is the test's own: ``.DS_Store`` excluded."""

    def setUp(self):
        super().setUp()
        excludes = self.base / "excludes"
        excludes.write_text(".DS_Store\n")
        config = self.base / "gitconfig"
        config.write_text(f"[core]\n\texcludesFile = {excludes}\n")
        patcher = mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": str(config)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.seed_add()
        self.alpha = self.rootstock / ALPHA_CLONE
        self.beta = self.rootstock / BETA_CLONE

    def exclude(self, clone: Path, *patterns: str) -> None:
        with (clone / ".git/info/exclude").open("a") as handle:
            handle.write("".join(f"{pattern}\n" for pattern in patterns))


class TestIgnoredFiles(IgnoredCase):
    def test_same_ignored_file_in_two_scions_is_no_conflict(self):
        for scion in ("kernel", "lib"):
            (self.alpha / scion / "scion/sys/.DS_Store").write_text("finder\n")
        code, _, err = self.graft()
        self.assertEqual(code, 0, err)
        self.assertFalse(os.path.lexists(self.trunk / "sys/.DS_Store"))
        self.assertEqual(self.real_paths(), oracle())

    def test_ignored_directory_is_not_created(self):
        self.exclude(self.beta, "build/")
        (self.beta / "scion/tools/build").mkdir()
        (self.beta / "scion/tools/build/out.o").write_text("object\n")
        code, _, err = self.graft()
        self.assertEqual(code, 0, err)
        self.assertFalse(os.path.lexists(self.trunk / "tools/build"))

    def test_untracked_file_that_is_not_ignored_is_grafted(self):
        self.exclude(self.beta, "*.o")
        (self.beta / "scion/tools/bin/new.c").write_text("new\n")
        (self.beta / "scion/tools/bin/new.o").write_text("object\n")
        code, _, err = self.graft()
        self.assertEqual(code, 0, err)
        self.assertTrue((self.trunk / "tools/bin/new.c").is_symlink())
        self.assertFalse(os.path.lexists(self.trunk / "tools/bin/new.o"))

    def test_tracked_file_matching_a_rule_is_grafted(self):
        self.exclude(self.beta, "*.sh")
        code, _, err = self.graft()
        self.assertEqual(code, 0, err)
        self.assertTrue((self.trunk / "tools/bin/tool.sh").is_symlink())
        self.assertEqual(self.real_paths(), oracle())

    def test_scion_outside_git_follows_the_global_rules(self):
        output = self.rootstock / BUILDING / "scion/building/output"
        (output / ".DS_Store").write_text("finder\n")
        (output / "result.bin").write_text("built\n")
        code, _, err = self.graft()
        self.assertEqual(code, 0, err)
        self.assertFalse(os.path.lexists(self.trunk / "building/output/.DS_Store"))
        self.assertTrue((self.trunk / "building/output/result.bin").is_symlink())

    def test_scion_outside_git_follows_its_own_gitignore(self):
        source = self.rootstock / BUILDING
        (source / ".gitignore").write_text("*.tmp\nstaging/\n")
        output = source / "scion/building/output"
        (output / "work.tmp").write_text("temporary\n")
        (output / "result.bin").write_text("built\n")
        (source / "scion/building/staging/lib/libx.a").write_text("archive\n")
        code, _, err = self.graft()
        self.assertEqual(code, 0, err)
        self.assertFalse(os.path.lexists(self.trunk / "building/output/work.tmp"))
        self.assertFalse(os.path.lexists(self.trunk / "building/staging"))
        self.assertTrue((self.trunk / "building/output/result.bin").is_symlink())

    def test_link_into_a_scion_outside_git_goes_on_regraft(self):
        output = self.rootstock / BUILDING / "scion/building/output"
        (output / "run.log").write_text("log\n")
        self.graft()
        self.assertTrue((self.trunk / "building/output/run.log").is_symlink())
        (self.rootstock / BUILDING / ".gitignore").write_text("*.log\n")
        code, _, err = run("graft", "--scion", "local@building", cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.assertFalse(os.path.lexists(self.trunk / "building/output/run.log"))

    def test_scion_outside_git_is_left_untouched_and_exclusions_logged(self):
        source = self.rootstock / BUILDING
        (source / "scion/building/output/.DS_Store").write_text("finder\n")
        before = sorted(source.rglob("*"))
        with self.assertLogs("scion.graft", level="DEBUG") as logs:
            code, _, err = self.graft()
        self.assertEqual(code, 0, err)
        self.assertEqual(sorted(source.rglob("*")), before)
        self.assertTrue(any("local/building building/output/.DS_Store" in line
                            for line in logs.output))

    def test_rules_of_a_repository_holding_the_rootstock_do_not_apply(self):
        subprocess.run(["git", "init", "-q"], cwd=self.base, check=True)
        (self.base / ".gitignore").write_text("rootstock/depots/\n")
        output = self.rootstock / "depots/generation/building/scion/building/output"
        (output / "result.bin").write_text("built\n")
        code, _, err = self.graft()
        self.assertEqual(code, 0, err)
        self.assertTrue((self.trunk / "building/output/result.bin").is_symlink())
        self.assertTrue((self.trunk / "tools/bin/tool.sh").is_symlink())

    def test_link_to_a_file_now_ignored_goes_on_regraft(self):
        (self.beta / "scion/tools/bin/run.log").write_text("log\n")
        self.graft()
        self.assertTrue((self.trunk / "tools/bin/run.log").is_symlink())
        self.exclude(self.beta, "*.log")
        code, _, err = run("graft", "--scion", "beta@tools::bin", cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.assertFalse(os.path.lexists(self.trunk / "tools/bin/run.log"))
        self.assertTrue((self.trunk / "tools/bin/tool.sh").is_symlink())

    def test_exclusions_are_logged(self):
        (self.beta / "scion/tools/.DS_Store").write_text("finder\n")
        with self.assertLogs("scion.graft", level="DEBUG") as logs:
            code, _, err = self.graft()
        self.assertEqual(code, 0, err)
        self.assertTrue(any("beta/tools::bin tools/.DS_Store" in line for line in logs.output))
        self.assertTrue(any("1 chemin(s) ignoré(s) par git" in line for line in logs.output))

    def test_clones_stay_clean(self):
        (self.beta / "scion/tools/.DS_Store").write_text("finder\n")
        self.graft()
        self.assertEqual(self.dirty_clones(), {})


if __name__ == "__main__":
    unittest.main()
