"""Conservation mirrors (doc/projection-miroir.md, part B).

One case per rule of the specification, named after it. Upstreams and mirrors
are local repositories reached through ``file://localhost`` URLs; nothing goes
over the network.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import make_fixture
from support import run
from test_projection import CarrierCase, write

from scion import gitops
from scion.model import read_grafted


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t", *args],
        cwd=repo, check=True, capture_output=True, text=True,
    ).stdout.strip()


def url(repo: Path) -> str:
    return "file://localhost" + str(repo)


def refs(repo: Path) -> dict[str, str]:
    """Branches and tags of a repository: ref name -> object id."""
    out = git(repo, "for-each-ref", "--format=%(refname) %(objectname)",
              "refs/heads", "refs/tags")
    return dict(line.split() for line in out.splitlines())


def all_refs(repo: Path) -> dict[str, str]:
    out = git(repo, "for-each-ref", "--format=%(refname) %(objectname)")
    return dict(line.split() for line in out.splitlines())


def commit_on(repo: Path, name: str, text: str = "x\n") -> str:
    write(repo / name, text)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", f"add {name}")
    return git(repo, "rev-parse", "HEAD")


class MirrorCase(unittest.TestCase):
    """A rootstock, an upstream with branches and tags, an empty bare mirror, a seed."""

    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="scion-mirror-")).resolve()
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.rootstock = self.base / "rootstock"
        (self.rootstock / "depots").mkdir(parents=True)
        (self.rootstock / ".scion.rootstock.signature").touch()
        (self.rootstock / "trunk").mkdir()
        (self.rootstock / "trunk/.scion.grafted.list").touch()
        self.upstream = self.new_upstream("upstream")
        self.mirror = self.new_mirror("mirror.git")
        self.seed_dir = self.base / "seed"
        self.dot = self.seed_dir / "scion/.scion"
        self.declare((self.mirror, self.upstream))

    # -- repositories --------------------------------------------------------
    def new_upstream(self, name: str) -> Path:
        repo = self.base / "repos" / name
        make_fixture.make_repo(repo, {"README.md": "amont\n"})
        self.first = git(repo, "rev-parse", "HEAD")
        git(repo, "tag", "-a", "v1.0", "-m", "v1.0")
        git(repo, "tag", "light")
        git(repo, "switch", "-q", "-c", "dev")
        self.dev = commit_on(repo, "dev.c")
        git(repo, "switch", "-q", "master")
        self.second = commit_on(repo, "second.c")
        return repo

    def new_mirror(self, name: str) -> Path:
        repo = self.base / "mirrors" / name
        repo.mkdir(parents=True)
        git(repo, "init", "-q", "--bare")
        return repo

    def declare(self, *pairs, dot: Path | None = None) -> None:
        write((dot or self.dot) / ".scion.mirrors",
              "".join(f"{url(m)}\t{url(u)}\n" for m, u in pairs))

    # -- commands ------------------------------------------------------------
    def sync(self, *args: str, expect: int | None = 0, seed: bool = True) -> tuple[int, str]:
        argv = ["mirror-sync", *(["--seed", str(self.seed_dir)] if seed else []), *args]
        code, _, err = run(*argv, cwd=self.rootstock)
        if expect is not None:
            self.assertEqual(code, expect, err)
        return code, err

    def sync_logged(self, *args: str, expect: int = 0, level: str = "INFO") -> list[str]:
        with self.assertLogs("scion.mirror", level=level) as logs:
            self.sync(*args, expect=expect)
        return logs.output

    def work(self, mirror: Path | None = None) -> Path:
        return self.rootstock / "depots/.mirrors/localhost" / str(mirror or self.mirror).lstrip("/")


class TestGraft(CarrierCase):
    """M-D2, M-D5: the graft reads the mirrors file for its error messages only."""

    def mirror_of_tiers(self, synced: bool) -> Path:
        mirror = self.base / "mirrors/hal.git"
        mirror.mkdir(parents=True)
        git(mirror, "init", "-q", "--bare")
        if synced:
            git(self.tiers.path, "push", "-q", url(mirror), "refs/heads/*:refs/heads/*",
                "refs/tags/*:refs/tags/*")
        return mirror

    def test_greffe_ne_lit_pas_mirrors(self):
        """M-D2: the graft clones the mirror named by the sources; a broken file changes nothing."""
        mirror = self.mirror_of_tiers(synced=True)
        self.seed("tiers hal Inc/* scion/inc/\n", location=url(mirror))
        write(self.dot / ".scion.mirrors", "une seule colonne\n")
        self.seed_add()
        self.graft()
        clone = self.clone()
        self.assertEqual(git(clone, "remote", "get-url", "origin"), url(mirror))
        self.assertIn("inc/a.h", self.links())

    def test_echec_clone_miroir_suggere_mirror_sync(self):
        """M-D5: a projected key whose version the (empty) mirror lacks."""
        mirror = self.mirror_of_tiers(synced=False)
        self.seed("tiers hal Inc/* scion/inc/\n", location=url(mirror))
        write(self.dot / ".scion.mirrors", f"{url(mirror)} {url(self.tiers.path)}\n")
        err = self.seed_add(expect=1)
        self.assertIn("mirror-sync", err)
        self.assertIn(url(self.tiers.path), err)

    def test_echec_clone_miroir_absent_suggere_mirror_sync(self):
        """M-D5: an ordinary scion whose mirror cannot be cloned."""
        missing = self.base / "mirrors/absent.git"
        write(self.dot / ".scion.sources.list", f"own plain master {url(missing)}\n")
        write(self.dot / ".scion.ramifications", "own plain master\n")
        write(self.dot / ".scion.mirrors", f"{url(missing)} {url(self.tiers.path)}\n")
        err = self.seed_add(expect=2)
        self.assertIn("mirror-sync", err)

    def test_echec_clone_sans_miroir_message_inchange(self):
        """P-C1: without a mirrors file, the message does not mention mirror-sync."""
        missing = self.base / "mirrors/absent.git"
        write(self.dot / ".scion.sources.list", f"own plain master {url(missing)}\n")
        write(self.dot / ".scion.ramifications", "own plain master\n")
        err = self.seed_add(expect=2)
        self.assertNotIn("mirror-sync", err)

    def test_version_introuvable_dans_clone_suggere_mirror_sync(self):
        """M-D5: graft-update stops on a clone whose declared tag the mirror never had."""
        mirror = self.mirror_of_tiers(synced=True)
        self.seed("tiers hal Inc/* scion/inc/\n", location=url(mirror))
        write(self.dot / ".scion.mirrors", f"{url(mirror)} {url(self.tiers.path)}\n")
        self.seed_add()
        self.graft()
        git(self.clone(), "tag", "-d", "v1.0")
        code, _, err = run("graft-update", cwd=self.rootstock)
        self.assertEqual(code, 1, err)
        self.assertIn("mirror-sync", err)


if __name__ == "__main__":
    unittest.main()
