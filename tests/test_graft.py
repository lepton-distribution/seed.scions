"""Leaf grafting: same tree as before, clean clones, movable rootstock."""

from __future__ import annotations

import os
import shutil
import unittest
from pathlib import Path

from support import FixtureCase, oracle, run
from scion.model import read_grafted, write_grafted


def broken_links(trunk: Path) -> list[Path]:
    return [
        Path(dirpath) / name
        for dirpath, dirnames, filenames in os.walk(trunk, followlinks=False)
        for name in filenames + dirnames
        if (Path(dirpath) / name).is_symlink() and not (Path(dirpath) / name).exists()
    ]


class TestGraftedTree(FixtureCase):
    def setUp(self):
        super().setUp()
        self.seed_add()

    def test_tree_matches_the_old_tool(self):
        code, _, err = self.graft()
        self.assertEqual(code, 0, err)
        self.assertEqual(self.real_paths(), oracle())

    def test_directories_are_real_and_leaves_are_links(self):
        self.graft()
        self.assertTrue((self.trunk / "sys/root/src/kernel/core").is_dir())
        self.assertFalse((self.trunk / "sys/root/src/kernel/core").is_symlink())
        self.assertTrue((self.trunk / "sys/root/src/kernel/core/kernel.c").is_symlink())

    def test_links_are_relative(self):
        self.graft()
        target = os.readlink(self.trunk / "sys/root/src/kernel/core/kernel.c")
        self.assertFalse(os.path.isabs(target))
        self.assertTrue(target.startswith(".."))

    def test_clones_stay_clean(self):
        self.graft()
        self.assertEqual(self.dirty_clones(), {})

    def test_clones_stay_clean_after_ungraft(self):
        self.graft()
        code, _, err = run("ungraft", cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.dirty_clones(), {})

    def test_hidden_scion_directory_is_not_grafted(self):
        self.graft()
        self.assertFalse((self.trunk / ".scion").exists())
        self.assertNotIn("ignored.txt", [p.name for p in self.trunk.rglob("*")])

    def test_versioned_symlink_is_copied_not_followed(self):
        self.graft()
        link = self.trunk / "tools/bin/tool-link.sh"
        self.assertTrue(link.is_symlink())
        self.assertEqual(link.resolve().name, "tool.sh")

    def test_empty_directories_are_created(self):
        self.graft()
        for relative in ("building/projects", "building/staging/lib", "building/output"):
            self.assertTrue((self.trunk / relative).is_dir(), relative)

    def test_order_of_the_grafted_list_does_not_matter(self):
        self.graft()
        first = self.real_paths()
        run("ungraft", cwd=self.rootstock)
        entries = list(read_grafted(self.rootstock / "trunk/.scion.grafted.list").values())
        write_grafted(self.rootstock / "trunk/.scion.grafted.list", reversed(entries))
        code, _, err = self.graft()
        self.assertEqual(code, 0, err)
        self.assertEqual(self.real_paths(), first)

    def test_graft_from_any_subdirectory(self):
        self.graft()
        expected = self.real_paths()
        run("ungraft", cwd=self.rootstock)
        deep = self.rootstock / "depots/generation/building/scion/building/projects"
        code, _, err = run("graft", cwd=deep)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.real_paths(), expected)

    def test_a_moved_rootstock_keeps_working(self):
        self.graft()
        moved = self.base / "moved"
        shutil.move(str(self.rootstock), str(moved))
        self.assertEqual(broken_links(moved / "trunk"), [])
        code, _, err = run("graft", cwd=moved / "trunk")
        self.assertEqual(code, 0, err)
        self.assertEqual(broken_links(moved / "trunk"), [])


class TestConflicts(FixtureCase):
    def setUp(self):
        super().setUp()
        self.seed_add()
        self.seed_add(self.fx.seed_conflict)

    def test_conflict_is_reported_with_both_origins(self):
        code, _, err = self.graft()
        self.assertEqual(code, 1)
        self.assertIn("sys/root/include/kernel.h", err)
        self.assertIn("alpha/core::kernel", err)
        self.assertIn("gamma/x::dup", err)

    def test_nothing_is_left_behind(self):
        self.graft()
        left = [p for p in self.trunk.rglob("*") if p.name != ".scion.grafted.list"]
        self.assertEqual(left, [])

    def test_no_silent_first_wins(self):
        code, out, _ = self.graft()
        self.assertNotEqual(code, 0)
        self.assertFalse((self.trunk / "sys/root/src/kernel/core/kernel.c").exists())


class TestFileDirectoryConflicts(FixtureCase):
    """A file, a link and a directory competing for the same trunk path."""

    def graft_pair(self, make_a, make_b) -> tuple[int, str, str]:
        depots = self.rootstock / "depots"
        make_a(depots / "a/scion")
        make_b(depots / "b/scion")
        seed = self.base / "seed-pair/scion/.scion"
        seed.mkdir(parents=True)
        (seed / ".scion.sources.list").write_text("t a * depots/a\nt b * depots/b\n")
        (seed / ".scion.ramifications").write_text("t a *\nt b *\n")
        code, _, err = run("seed-clone", "--seed", str(seed.parent), cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        return self.graft()

    @staticmethod
    def file_x(stem: Path) -> None:
        stem.mkdir(parents=True)
        (stem / "X").write_text("file\n")

    @staticmethod
    def directory_x(stem: Path) -> None:
        (stem / "X").mkdir(parents=True)
        (stem / "X/y").write_text("y\n")

    @staticmethod
    def link_x(stem: Path) -> None:
        (stem / "d").mkdir(parents=True)
        (stem / "X").symlink_to("d")

    def assert_clean_failure(self, code: int, err: str) -> None:
        self.assertEqual(code, 1, err)
        self.assertIn("X : déjà fourni par « t/a », réclamé par « t/b »", err)
        left = [p for p in self.trunk.rglob("*") if p.name != ".scion.grafted.list"]
        self.assertEqual(left, [])

    def test_file_then_directory(self):
        code, _, err = self.graft_pair(self.file_x, self.directory_x)
        self.assert_clean_failure(code, err)

    def test_versioned_link_then_directory_never_writes_in_a_clone(self):
        code, _, err = self.graft_pair(self.link_x, self.directory_x)
        self.assert_clean_failure(code, err)
        self.assertEqual(os.listdir(self.rootstock / "depots/a/scion/d"), [])

    def test_directory_then_file_names_its_owner(self):
        code, _, err = self.graft_pair(self.directory_x, self.file_x)
        self.assert_clean_failure(code, err)


class TestUngraft(FixtureCase):
    def setUp(self):
        super().setUp()
        self.seed_add()
        self.graft()

    def test_grafted_list_is_preserved(self):
        run("ungraft", cwd=self.rootstock)
        self.assertTrue((self.trunk / ".scion.grafted.list").exists())
        self.assertTrue((self.trunk / ".scion.grafted.list").read_text())

    def test_trunk_is_emptied(self):
        run("ungraft", cwd=self.rootstock)
        left = [p for p in self.trunk.rglob("*") if p.name != ".scion.grafted.list"]
        self.assertEqual(left, [])

    def test_user_data_stops_the_ungraft(self):
        (self.trunk / "sys/notes.txt").write_text("mine\n")
        code, _, err = run("ungraft", cwd=self.rootstock)
        self.assertEqual(code, 1)
        self.assertIn("sys/notes.txt", err)
        self.assertTrue((self.trunk / "sys/notes.txt").exists())
        self.assertTrue((self.trunk / "sys/root/src/kernel/core/kernel.c").is_symlink())

    def test_force_keeps_user_data_and_removes_the_rest(self):
        (self.trunk / "sys/notes.txt").write_text("mine\n")
        code, _, err = run("ungraft", "--force", cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.assertTrue((self.trunk / "sys/notes.txt").exists())
        self.assertFalse((self.trunk / "tools").exists())

    def test_graft_force_keeps_user_data_and_regrafts(self):
        (self.trunk / "sys/notes.txt").write_text("mine\n")
        code, _, err = run("graft", "--force", cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.assertTrue((self.trunk / "sys/notes.txt").exists())
        self.assertTrue((self.trunk / "sys/root/src/kernel/core/kernel.c").is_symlink())

    def test_graft_clean_empties_the_list_but_keeps_the_marker(self):
        code, _, err = run("graft-clean", cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.assertTrue((self.trunk / ".scion.grafted.list").exists())
        self.assertEqual((self.trunk / ".scion.grafted.list").read_text(), "")
        # the rootstock is still discoverable afterwards
        self.assertEqual(run("rootstock-information", cwd=self.rootstock)[0], 0)


class TestGraftUpdate(FixtureCase):
    def test_graft_update_pulls_and_regrafts(self):
        self.seed_add()
        self.graft()
        code, _, err = run("graft-update", cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.real_paths(), oracle())
        self.assertEqual(self.dirty_clones(), {})


if __name__ == "__main__":
    unittest.main()
