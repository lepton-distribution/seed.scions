"""Integration against the real Lepton seed. Needs the network, so it is opt-in.

    SCION_TEST_NETWORK=1 python3 -m unittest discover -s tests -p test_network.py

This runs the sequence the README documents, against the published seed, with
no local patching: it is therefore also the check that the correction of
``.scion.sources.list`` has landed on the ``original-tree`` branch of
lepton-seed.scions. Until that commit is pushed, the seed still carries
``$SCION_ROOTSTOCK/depots/generation/building`` and this test fails on it.

The rejection of that form is covered without the network by
``test_seed.TestEnvironmentVariableRejected``, on a copy of the real file.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from support import run

SEED_URL = "https://github.com/lepton-distribution/lepton-seed.scions.git"
SEED_VERSION = "original-tree"


@unittest.skipUnless(
    os.environ.get("SCION_TEST_NETWORK"),
    "réseau désactivé ; exportez SCION_TEST_NETWORK=1 pour l'activer",
)
class TestLeptonTree(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="scion-network-"))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.rootstock = self.base / "rootstock"
        self.rootstock.mkdir()
        code, _, err = run("rootstock-install", cwd=self.rootstock)
        self.assertEqual(code, 0, err)

    def test_full_tree(self):
        code, _, err = run(
            "seed-add", "--version", SEED_VERSION, SEED_URL, cwd=self.rootstock
        )
        self.assertEqual(
            code, 0,
            f"{err}\nSi l'erreur porte sur une variable d'environnement, la "
            f"correction de .scion.sources.list n'est pas encore poussée sur "
            f"la branche {SEED_VERSION} de lepton-seed.scions.",
        )
        code, _, err = run("graft", cwd=self.rootstock)
        self.assertEqual(code, 0, err)

        self.assertTrue(
            (self.rootstock / "depots/lepton-seed.scions" / SEED_VERSION / ".git").is_dir()
        )

        trunk = self.rootstock / "trunk"
        self.assertTrue((trunk / "sys/root/src").is_dir())
        self.assertTrue((trunk / "tools/bin/mklepton_gnu").is_symlink())
        self.assertTrue((trunk / "building/projects").is_dir())
        # directories are real, leaves are relative links
        self.assertFalse((trunk / "sys/root/src").is_symlink())
        self.assertFalse(os.path.isabs(os.readlink(trunk / "tools/bin/mklepton_gnu")))

        clone = self.rootstock / "depots/lepton/original/master"
        self.assertTrue((clone / ".git").is_dir())
        status = subprocess.run(
            ["git", "status", "--porcelain"], cwd=clone,
            capture_output=True, text=True, check=True,
        ).stdout
        self.assertEqual(status, "")


if __name__ == "__main__":
    unittest.main()
