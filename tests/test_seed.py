"""The real lepton seed, and the rejection of the ``$SCION_ROOTSTOCK`` form."""

from __future__ import annotations

import unittest

from support import DATA, FixtureCase, run
from scion.errors import ScionError
from scion.model import read_ramifications, read_sources, select_source
from scion.rootstock import Rootstock


class TestOriginalTreeSeed(unittest.TestCase):
    """The corrected seed of lepton-seed.scions, branch original-tree."""

    def setUp(self):
        self.refs = read_ramifications(DATA / "original-tree.ramifications")
        self.sources = read_sources(DATA / "original-tree.sources.list")
        self.rootstock = Rootstock(DATA / "nowhere", "trunk")

    def test_every_ramification_resolves(self):
        for ref in self.refs:
            select_source(self.sources, ref)

    def test_local_path_is_relative_to_the_rootstock(self):
        ref = next(r for r in self.refs if r.key == "lepton/building")
        source = select_source(self.sources, ref)
        self.assertEqual(
            self.rootstock.resolve(source.location),
            self.rootstock.path / "depots/generation/building",
        )

    def test_remote_scion_has_no_subpath(self):
        ref = next(r for r in self.refs if r.key == "lepton/original::tree")
        self.assertEqual(select_source(self.sources, ref).subpath, "")


class TestEnvironmentVariableRejected(unittest.TestCase):
    """The uncorrected seed must fail with an actionable message."""

    def test_message_names_the_replacement(self):
        sources = read_sources(DATA / "bad-envvar.sources.list")
        local = next(s for s in sources if s.ref.key == "lepton/building")
        rootstock = Rootstock(DATA / "nowhere", "trunk")
        with self.assertRaises(ScionError) as caught:
            rootstock.resolve(local.location)
        message = str(caught.exception)
        self.assertIn("variables d'environnement", message)
        self.assertIn("depots/generation/building", message)

    def test_no_environment_expansion_happens(self):
        import os

        sources = read_sources(DATA / "bad-envvar.sources.list")
        local = next(s for s in sources if s.ref.key == "lepton/building")
        self.assertNotIn("SCION_ROOTSTOCK", os.environ)
        self.assertTrue(local.location.startswith("$SCION_ROOTSTOCK/"))


class TestSeedOnRootstock(FixtureCase):
    def test_seed_add_writes_relative_paths(self):
        self.seed_add()
        lines = self.rootstock.joinpath("trunk/.scion.grafted.list").read_text().splitlines()
        locations = [line.split()[3] for line in lines]
        self.assertEqual(
            locations,
            [
                "depots/alpha/core/master/kernel",
                "depots/alpha/core/master/lib",
                "depots/beta/tools/master",
                "depots/generation/building",
            ],
        )

    def test_one_clone_for_two_scions_of_the_same_repository(self):
        self.seed_add()
        self.assertEqual(len(self.fx.clones()), 2)

    def test_question_mark_version_picks_the_highest(self):
        code, _, err = run("seed-add", str(self.fx.seed_assets), cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        line = self.rootstock.joinpath("trunk/.scion.grafted.list").read_text().split()
        self.assertEqual(line[2], "1.2")
        self.assertEqual(line[3], "depots/generation/assets/1.2")

    def test_seed_with_an_environment_variable_is_refused(self):
        bad = self.fx.seed / "scion/.scion/.scion.sources.list"
        bad.write_text(
            bad.read_text().replace(
                "depots/generation/building", "$SCION_ROOTSTOCK/depots/generation/building"
            )
        )
        code, _, err = run("seed-add", str(self.fx.seed), cwd=self.rootstock)
        self.assertEqual(code, 1)
        self.assertIn("variables d'environnement", err)


if __name__ == "__main__":
    unittest.main()
