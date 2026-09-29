"""The ``.scion.*`` formats, read from the real files of lepton-seed.scions."""

from __future__ import annotations

import unittest

from support import DATA
from scion.model import (
    ScionRef,
    SourceEntry,
    compare,
    read_ramifications,
    read_sources,
    select_source,
)


class TestRamifications(unittest.TestCase):
    def test_original_tree(self):
        refs = read_ramifications(DATA / "original-tree.ramifications")
        self.assertEqual(
            [(r.key, r.version) for r in refs],
            [("lepton/original::tree", "master"), ("lepton/building", "*")],
        )

    def test_scion_without_suffix(self):
        """``building`` has no ``::`` -- the old split() crashed on that."""
        ref = read_ramifications(DATA / "original-tree.ramifications")[1]
        self.assertEqual((ref.prefix, ref.suffix), ("building", None))
        self.assertEqual(ref.name, "building")

    def test_master_has_every_scion(self):
        refs = read_ramifications(DATA / "master.ramifications")
        keys = [r.key for r in refs]
        self.assertEqual(len(keys), 20)
        self.assertEqual(len(set(keys)), 20)
        # same suffix on two different prefixes must stay distinct
        self.assertIn("lepton/root::executive-base", keys)
        self.assertIn("lepton/gnu::executive-base", keys)

    def test_blank_lines_and_padding(self):
        """The real files mix spaces and tabs and hold blank lines."""
        refs = read_ramifications(DATA / "master.ramifications")
        self.assertTrue(all(" " not in r.version for r in refs))


class TestSources(unittest.TestCase):
    def test_missing_subpath_column(self):
        """``original::tree`` keeps its scion/ at the root of the clone."""
        entries = read_sources(DATA / "original-tree.sources.list")
        remote = next(e for e in entries if e.ref.key == "lepton/original::tree")
        self.assertEqual(remote.subpath, "")
        self.assertTrue(remote.location.endswith("lepton-original-tree.scions.git"))

    def test_subpath_column(self):
        entries = read_sources(DATA / "master.sources.list")
        kernel = next(e for e in entries if e.ref.key == "lepton/root::kernel")
        self.assertEqual(kernel.subpath, "kernel")
        bsp = next(e for e in entries if e.ref.key == "lepton/root::discovery-f4")
        self.assertEqual(bsp.subpath, "bsp/stm32f4/discovery_f4")

    def test_one_repository_for_sixteen_scions(self):
        entries = read_sources(DATA / "master.sources.list")
        root = {e.location for e in entries if e.ref.prefix == "root"}
        self.assertEqual(len(root), 1)

    def test_comments_and_short_lines_are_ignored(self):
        entries = read_sources(DATA / "original-tree.sources.list")
        self.assertEqual(len(entries), 2)
        self.assertNotIn("#shelf", [e.ref.shelf for e in entries])

    def test_local_entry_keeps_its_relative_path(self):
        entries = read_sources(DATA / "original-tree.sources.list")
        local = next(e for e in entries if e.ref.key == "lepton/building")
        self.assertEqual(local.location, "depots/generation/building")
        self.assertEqual(local.ref.version, "*")


class TestCompare(unittest.TestCase):
    def test_numeric(self):
        self.assertEqual(compare("1.1.2", "1.1.2"), 0)
        self.assertEqual(compare("1.2.2", "1.1.2"), 1)
        self.assertEqual(compare("1.1.2", "1.2.2"), -1)

    def test_alphanumeric(self):
        self.assertEqual(compare("1.1.beta2", "1.1.beta1"), 1)
        self.assertEqual(compare("1.1.beta1", "1.1.beta2"), -1)

    def test_mixed_shapes_are_not_comparable(self):
        """int against list: kept lenient, as the old tool was."""
        self.assertEqual(compare("1.0", "beta13"), 0)

    def test_placeholder_versions(self):
        self.assertEqual(compare("master", "master"), 0)
        self.assertEqual(compare("*", "*"), 0)


class TestSelect(unittest.TestCase):
    def setUp(self):
        self.sources = read_sources(DATA / "master.sources.list")

    def test_exact_version(self):
        ref = ScionRef.parse("lepton", "root::kernel", "master")
        self.assertEqual(select_source(self.sources, ref).subpath, "kernel")

    def test_question_mark_takes_the_highest(self):
        sources = [
            SourceEntry(ScionRef.parse("local", "gen::assets", v), f"depots/assets/{v}")
            for v in ("1.0", "1.12", "1.2")
        ]
        ref = ScionRef.parse("local", "gen::assets", "?")
        self.assertEqual(select_source(sources, ref).ref.version, "1.12")

    def test_exact_version_wins_over_a_higher_one(self):
        sources = [
            SourceEntry(ScionRef.parse("local", "gen::assets", v), f"depots/assets/{v}")
            for v in ("1.0", "1.12")
        ]
        ref = ScionRef.parse("local", "gen::assets", "1.0")
        self.assertEqual(select_source(sources, ref).location, "depots/assets/1.0")

    def test_unknown_scion(self):
        ref = ScionRef.parse("lepton", "root::nowhere", "master")
        with self.assertRaises(Exception) as caught:
            select_source(self.sources, ref)
        self.assertIn("root::nowhere", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
