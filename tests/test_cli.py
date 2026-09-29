"""Exit codes, rootstock discovery and argument handling."""

from __future__ import annotations

import unittest

from support import FixtureCase, run
from scion import __version__
from scion.rootstock import INSTALL_LAYOUT, SIGNATURE


class TestVersion(unittest.TestCase):
    def test_version_is_the_package_one(self):
        code, out, _ = run("version")
        self.assertEqual(code, 0)
        self.assertIn(__version__, out)
        self.assertEqual(__version__, "0.5.0.1")

    def test_no_command_prints_help(self):
        code, out, _ = run()
        self.assertEqual(code, 0)
        self.assertIn("rootstock-install", out)


class TestDiscovery(FixtureCase):
    def test_from_a_subdirectory(self):
        deep = self.rootstock / "depots/generation/building/scion/building/output"
        code, out, err = run("rootstock-information", cwd=deep)
        self.assertEqual(code, 0, err)
        self.assertIn(str(self.rootstock), out)
        self.assertIn("trunk", out)

    def test_outside_any_rootstock(self):
        code, _, err = run("graft", cwd=self.fx.repos)
        self.assertEqual(code, 1)
        self.assertIn(SIGNATURE, err)

    def test_explicit_path_must_carry_the_signature(self):
        code, _, err = run("graft", str(self.fx.repos), cwd=self.rootstock)
        self.assertEqual(code, 1)
        self.assertIn(SIGNATURE, err)

    def test_uninitialised_rootstock(self):
        (self.rootstock / "trunk/.scion.grafted.list").unlink()
        (self.rootstock / "trunk").rmdir()
        code, _, err = run("graft", cwd=self.rootstock)
        self.assertEqual(code, 1)
        self.assertIn("non initialisé", err)

    def test_ambiguous_trunk(self):
        other = self.rootstock / "other-trunk"
        other.mkdir()
        (other / ".scion.grafted.list").touch()
        code, _, err = run("rootstock-information", cwd=self.rootstock)
        self.assertEqual(code, 1)
        self.assertIn("ambigu", err)

    def test_trunk_option_lifts_the_ambiguity(self):
        other = self.rootstock / "other-trunk"
        other.mkdir()
        (other / ".scion.grafted.list").touch()
        code, out, err = run("rootstock-information", "--trunk", "trunk", cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.assertIn("trunk: trunk", out)


class TestInstall(FixtureCase):
    def test_install_creates_the_generic_layout(self):
        target = self.base / "fresh"
        target.mkdir()
        code, _, err = run("rootstock-install", cwd=target)
        self.assertEqual(code, 0, err)
        self.assertTrue((target / SIGNATURE).exists())
        self.assertTrue((target / "trunk/.scion.grafted.list").exists())
        for relative in INSTALL_LAYOUT:
            self.assertTrue((target / relative).is_dir(), relative)

    def test_install_names_the_trunk(self):
        target = self.base / "fresh-named"
        target.mkdir()
        code, _, err = run("rootstock-install", "--trunk", "tree", cwd=target)
        self.assertEqual(code, 0, err)
        self.assertTrue((target / "tree/.scion.grafted.list").exists())

    def test_install_refuses_a_populated_directory(self):
        code, _, err = run("rootstock-install", cwd=self.rootstock)
        self.assertEqual(code, 1)
        self.assertIn("pas vide", err)

    def test_no_lepton_layout_is_created(self):
        target = self.base / "fresh-generic"
        target.mkdir()
        run("rootstock-install", cwd=target)
        self.assertFalse((target / "depots/lepton").exists())


class TestGitCommand(FixtureCase):
    def setUp(self):
        super().setUp()
        self.seed_add()

    def test_successful_command(self):
        code, _, err = run(
            "git", "--key", "alpha@core::kernel",
            "--args", "rev-parse --is-inside-work-tree", cwd=self.rootstock,
        )
        self.assertEqual(code, 0, err)

    def test_failing_git_command_returns_two(self):
        code, _, err = run(
            "git", "--key", "alpha@core::kernel", "--args", "frobnicate --now",
            cwd=self.rootstock,
        )
        self.assertEqual(code, 2)

    def test_unknown_key_is_a_user_error(self):
        code, _, err = run(
            "git", "--key", "alpha@core::nowhere", "--args", "status", cwd=self.rootstock
        )
        self.assertEqual(code, 1)
        self.assertIn("core::nowhere", err)

    def test_args_are_split_like_a_shell_without_a_shell(self):
        code, _, err = run(
            "git", "--key", "alpha@core::kernel",
            "--args", "log -1 --format=%s", cwd=self.rootstock,
        )
        self.assertEqual(code, 0, err)


class TestSeedOptions(FixtureCase):
    def test_single_branch_spelt_both_ways(self):
        for flag in ("--single_branch", "--single-branch"):
            with self.subTest(flag=flag):
                code, _, err = run(
                    "seed-add", flag, str(self.fx.seed), cwd=self.rootstock
                )
                self.assertEqual(code, 0, err)

    def test_seed_add_without_a_url(self):
        code, _, err = run("seed-add", cwd=self.rootstock)
        self.assertEqual(code, 1)
        self.assertIn("seed-add", err)

    def test_graft_without_a_seed(self):
        code, _, err = run("graft", cwd=self.rootstock)
        self.assertEqual(code, 1)
        self.assertIn("seed-add", err)

    def test_seed_clone_needs_a_seed_outside_a_scion_directory(self):
        code, _, err = run("seed-clone", cwd=self.rootstock)
        self.assertEqual(code, 1)
        self.assertIn("--seed", err)

    def test_seed_clone_and_seed_update(self):
        code, _, err = run("seed-clone", "--seed", str(self.fx.seed), cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        code, _, err = run("seed-update", "--seed", str(self.fx.seed), cwd=self.rootstock)
        self.assertEqual(code, 0, err)


if __name__ == "__main__":
    unittest.main()
