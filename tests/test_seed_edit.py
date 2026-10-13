"""Declaring and forgetting scions in a seed, then grafting the result."""

from __future__ import annotations

import os
import unittest

import make_fixture
from support import FixtureCase, run
from scion.model import read_grafted

SOURCES = "scion/.scion/.scion.sources.list"
RAMIFICATIONS = "scion/.scion/.scion.ramifications"


class SeedCase(FixtureCase):
    def setUp(self):
        super().setUp()
        self.sources = self.fx.seed / SOURCES
        self.ramifications = self.fx.seed / RAMIFICATIONS
        delta = self.fx.repos / "delta"
        make_fixture._write(delta / "scion/delta/delta.txt", "delta\n")
        make_fixture._make_repo(delta)
        self.delta_url = make_fixture._url(delta)

    def seed_run(self, *argv: str) -> tuple[int, str, str]:
        return run(argv[0], "--seed", str(self.fx.seed), *argv[1:], cwd=self.rootstock)

    def lines_of(self, path, key_fields: tuple[str, str]) -> list[list[str]]:
        return [
            line.split() for line in path.read_text().splitlines()
            if line.split()[:2] == list(key_fields)
        ]


class TestSeedScionAdd(SeedCase):
    def test_adds_one_line_to_each_list_and_keeps_the_rest(self):
        before_sources = self.sources.read_text()
        before_ramifications = self.ramifications.read_text()
        code, _, err = self.seed_run("seed-scion-add", "delta@d::x", "master", self.delta_url)
        self.assertEqual(code, 0, err)
        self.assertEqual(
            self.sources.read_text(), before_sources + f"delta\td::x\tmaster\t{self.delta_url}\n"
        )
        self.assertEqual(
            self.ramifications.read_text(), before_ramifications + "delta\td::x\tmaster\n"
        )

    def test_subpath_column(self):
        code, _, err = self.seed_run(
            "seed-scion-add", "alpha@core::extra", "master", self.delta_url, "extra"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(
            self.lines_of(self.sources, ("alpha", "core::extra")),
            [["alpha", "core::extra", "master", self.delta_url, "extra"]],
        )

    def test_a_declared_scion_is_refused(self):
        before = self.sources.read_text()
        code, _, err = self.seed_run("seed-scion-add", "alpha@core::lib", "dev", self.delta_url)
        self.assertEqual(code, 1)
        self.assertIn("--replace", err)
        self.assertEqual(self.sources.read_text(), before)

    def test_replace(self):
        code, _, err = self.seed_run(
            "seed-scion-add", "--replace", "alpha@core::lib", "dev", self.delta_url
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(self.lines_of(self.sources, ("alpha", "core::lib")),
                         [["alpha", "core::lib", "dev", self.delta_url]])
        self.assertEqual(self.lines_of(self.ramifications, ("alpha", "core::lib")),
                         [["alpha", "core::lib", "dev"]])
        self.assertEqual(len(self.lines_of(self.sources, ("alpha", "core::kernel"))), 1)

    def test_environment_variable_is_refused(self):
        code, _, err = self.seed_run("seed-scion-add", "x@y", "*", "$HOME/y")
        self.assertEqual(code, 1)
        self.assertIn("variables d'environnement", err)

    def test_invalid_key_and_fields(self):
        for argv in (("nokey", "master", "a"), ("a@", "master", "a"), ("a@b", "ma ster", "a")):
            with self.subTest(argv=argv):
                code, _, err = self.seed_run("seed-scion-add", *argv)
                self.assertEqual(code, 1, err)

    def test_seed_found_from_its_scion_directory(self):
        code, _, err = run("seed-scion-add", "delta@d::x", "master", self.delta_url,
                           cwd=self.fx.seed / "scion")
        self.assertEqual(code, 0, err)

    def test_added_scion_clones_and_grafts(self):
        self.seed_add()
        self.assertEqual(self.graft()[0], 0)
        self.seed_run("seed-scion-add", "delta@d::x", "master", self.delta_url)
        code, _, err = self.seed_run("seed-clone")
        self.assertEqual(code, 0, err)
        code, _, err = run("graft", "--scion", "delta@d::x", cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.assertTrue((self.trunk / "delta/delta.txt").is_symlink())


class TestSeedScionRemove(SeedCase):
    def test_removes_its_lines_only(self):
        code, _, err = self.seed_run("seed-scion-remove", "alpha@core::lib")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.lines_of(self.sources, ("alpha", "core::lib")), [])
        self.assertEqual(self.lines_of(self.ramifications, ("alpha", "core::lib")), [])
        text = self.sources.read_text()
        self.assertIn("#shelf", text)
        self.assertIn("truncated\tline\twithout", text)
        self.assertEqual(len(self.lines_of(self.sources, ("alpha", "core::kernel"))), 1)

    def test_absent_scion(self):
        code, _, err = self.seed_run("seed-scion-remove", "alpha@nowhere")
        self.assertEqual(code, 1)
        self.assertIn("alpha@nowhere", err)

    def test_removed_scion_stays_out_after_a_seed_clone(self):
        self.seed_add()
        self.graft()
        self.seed_run("seed-scion-remove", "beta@tools::bin")
        code, _, err = run("graft-remove", "beta@tools::bin", cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        code, _, err = self.seed_run("seed-clone")
        self.assertEqual(code, 0, err)
        self.assertNotIn("beta/tools::bin", read_grafted(self.trunk / ".scion.grafted.list"))
        self.assertEqual(self.graft()[0], 0)
        self.assertFalse(os.path.lexists(self.trunk / "tools"))


if __name__ == "__main__":
    unittest.main()
