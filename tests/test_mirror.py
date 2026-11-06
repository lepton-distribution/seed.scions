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


# ==========================================================================
# B.1 declaration
# ==========================================================================
class TestDeclaration(MirrorCase):
    def test_ligne_mirrors_mal_formee(self):
        """M-D3: wrong field count or a local path is an error with file and line."""
        write(self.dot / ".scion.mirrors",
              f"# commentaire\n\n{url(self.mirror)}\n"
              f"{url(self.mirror)} {url(self.upstream)} en-trop\n"
              f"{url(self.mirror)} {self.upstream}\n"
              f"file:///x {url(self.upstream)}\n")
        code, err = self.sync(expect=1)
        mirrors = self.dot / ".scion.mirrors"
        for number in (3, 4, 5, 6):
            self.assertIn(f"{mirrors}:{number}", err)
        self.assertNotIn(f"{mirrors}:1", err)
        self.assertEqual(refs(self.mirror), {})
        self.assertFalse((self.rootstock / "depots/.mirrors").exists())

    def test_miroir_deux_amonts_erreur(self):
        """M-D4: one mirror, two upstreams -- even in two files -- is an error."""
        other = self.new_upstream("other")
        self.declare((self.mirror, self.upstream), (self.mirror, other))
        code, err = self.sync(expect=1)
        self.assertIn(url(self.mirror), err)
        self.assertEqual(refs(self.mirror), {})

    def test_meme_amont_deux_miroirs_admis(self):
        """M-D4: an upstream may have several mirrors."""
        second = self.new_mirror("second.git")
        self.declare((self.mirror, self.upstream), (second, self.upstream))
        self.sync()
        self.assertEqual(refs(self.mirror), refs(self.upstream))
        self.assertEqual(refs(second), refs(self.upstream))

    def test_sans_miroir_declare(self):
        """Nothing declared: nothing done, code 0."""
        (self.dot / ".scion.mirrors").unlink()
        self.sync()
        self.assertFalse((self.rootstock / "depots/.mirrors").exists())


class TestCarrier(CarrierCase):
    def test_mirrors_dans_porteur(self):
        """M-D1, M-C1: the mirrors of the grafted seeds and of their carriers are synced."""
        upstream = self.tiers.path
        mirror = self.base / "mirrors/hal.git"
        mirror.mkdir(parents=True)
        git(mirror, "init", "-q", "--bare")
        repo = self.carrier()
        write(repo / "scion/.scion/.scion.mirrors", f"{url(mirror)} {url(upstream)}\n")
        make_fixture.commit_all(repo, "miroir")
        self.seed_with(repo)
        self.seed_add()
        code, _, err = run("mirror-sync", cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.assertEqual(refs(mirror), refs(upstream))

    def test_ordinaire_non_porteur_ignore(self):
        """M-D1, P-C3: the .scion/ of a scion without projections is not read."""
        mirror = self.base / "mirrors/hal.git"
        mirror.mkdir(parents=True)
        git(mirror, "init", "-q", "--bare")
        repo = self.base / "repos/plain"
        write(repo / "scion/plain/f.c", "f\n")
        write(repo / "scion/.scion/.scion.mirrors", f"{url(mirror)} {url(self.tiers.path)}\n")
        make_fixture.make_repo(repo, {})
        self.seed_with(repo)
        self.seed_add()
        code, _, err = run("mirror-sync", cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.assertEqual(refs(mirror), {})


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


# ==========================================================================
# B.2 command
# ==========================================================================
class TestCommand(MirrorCase):
    def test_premiere_synchronisation_miroir_vide(self):
        """M-R1, M-R6: an empty mirror receives every branch and tag of the upstream."""
        self.sync()
        self.assertEqual(refs(self.mirror), refs(self.upstream))

    def test_mirror_sync_url_inconnue_erreur_avant_tout(self):
        """M-C1, M-K1: an unknown URL is a usage error (2), before any network access."""
        code, err = self.sync(url(self.mirror), "file://localhost/inconnu-a",
                              "file://localhost/inconnu-b", expect=2)
        self.assertIn("inconnu-a", err)
        self.assertIn("inconnu-b", err)
        self.assertFalse((self.rootstock / "depots/.mirrors").exists())
        self.assertEqual(refs(self.mirror), {})

    def test_mirror_sync_selection(self):
        """M-C1: given URLs restrict the mirrors processed."""
        other = self.new_upstream("other")
        second = self.new_mirror("second.git")
        self.declare((self.mirror, self.upstream), (second, other))
        self.sync(url(second))
        self.assertEqual(refs(self.mirror), {})
        self.assertEqual(refs(second), refs(other))

    def test_rootstock_en_argument_avant_les_url(self):
        """B.2: ``mirror-sync [rootstock] [url…]`` -- a path first, then URLs."""
        code, _, err = run("mirror-sync", str(self.rootstock), "--seed", str(self.seed_dir),
                           url(self.mirror), cwd=self.base)
        self.assertEqual(code, 0, err)
        self.assertEqual(refs(self.mirror), refs(self.upstream))

    def test_depot_de_travail_refs_amont_separees(self):
        """M-C2: work repository under depots/.mirrors, upstream refs in refs/amont/*."""
        self.sync()
        work = self.work()
        self.assertTrue((work / "config").is_file())
        mine = all_refs(work)
        self.assertEqual(mine["refs/amont/heads/master"], self.second)
        self.assertIn("refs/amont/tags/v1.0", mine)
        self.assertEqual(git(work, "config", "--get-all", "remote.origin.fetch").split(),
                         ["+refs/heads/*:refs/heads/*", "+refs/tags/*:refs/tags/*"])
        with self.assertRaises(subprocess.CalledProcessError):
            git(work, "config", "--get", "remote.origin.mirror")
        # the upstream's tags never land in the mirror's namespace of the work repository
        commit_on(self.upstream, "third.c")
        git(self.upstream, "tag", "-a", "v3.0", "-m", "v3.0")
        self.sync("--dry-run")
        self.assertNotIn("refs/tags/v3.0", all_refs(work))
        self.assertIn("refs/amont/tags/v3.0", all_refs(work))

    def test_seules_branches_et_tags(self):
        """M-C3: other references of the upstream are not sent."""
        git(self.upstream, "update-ref", "refs/pull/1/head", self.dev)
        git(self.upstream, "notes", "add", "-m", "note", self.first)
        self.sync()
        mirrored = all_refs(self.mirror)
        self.assertFalse([name for name in mirrored
                          if not name.startswith(("refs/heads/", "refs/tags/"))])
        self.assertEqual(refs(self.mirror), refs(self.upstream))

    def test_push_sans_force_ni_suppression(self):
        """M-C4: pushes name each reference, to the URL, never forced nor deleting."""
        pushes: list[list[str]] = []
        real = gitops.run

        def spy(args, cwd=None):
            if args and args[0] == "push":
                pushes.append(args)
            return real(args, cwd)

        with mock.patch.object(gitops, "run", spy):
            self.sync()
            commit_on(self.upstream, "third.c")
            self.sync()
        self.assertEqual(len(pushes), 2)
        forbidden = {"--force", "-f", "--mirror", "--prune", "--atomic", "--delete", "-d",
                     "--all", "--tags", "--force-with-lease"}
        for args in pushes:
            self.assertEqual(args[:3], ["push", "--porcelain", url(self.mirror)])
            self.assertFalse(forbidden & set(args), args)
            for spec in args[3:]:
                source, _, target = spec.partition(":")
                self.assertFalse(spec.startswith("+"), spec)
                self.assertTrue(source.startswith("refs/amont/"), spec)
                self.assertTrue(target.startswith(("refs/heads/", "refs/tags/")), spec)
        self.assertEqual(pushes[1][3:], ["refs/amont/heads/master:refs/heads/master"])

    def test_miroir_inaccessible_signale_les_autres_traites(self):
        """M-C5: an unreachable mirror is reported (code 1); the others are synced."""
        missing = self.base / "mirrors/absent.git"
        second = self.new_mirror("second.git")
        self.declare((missing, self.upstream), (second, self.upstream))
        code, err = self.sync(expect=1)
        self.assertEqual(refs(second), refs(self.upstream))
        self.assertFalse(missing.exists())

    def test_amont_inaccessible_signale(self):
        """M-C5, M-K1: an unreachable upstream is reported too, nothing is sent."""
        self.declare((self.mirror, self.base / "repos/absent"))
        self.sync(expect=1)
        self.assertEqual(refs(self.mirror), {})

    def test_dry_run_rien_envoye(self):
        """M-C6: everything is computed and reported, nothing is sent."""
        output = self.sync_logged("--dry-run")
        self.assertEqual(refs(self.mirror), {})
        self.assertTrue((self.work() / "config").is_file())
        bilan = [line for line in output if "à envoyer" in line and "signalement" in line]
        self.assertEqual(len(bilan), 1, output)
        self.assertIn("4 référence(s)", bilan[0])


# ==========================================================================
# B.3 one rule per reference
# ==========================================================================
class TestReferences(MirrorCase):
    def setUp(self) -> None:
        super().setUp()
        self.sync()
        self.before = refs(self.mirror)

    def test_branche_nouvelle(self):
        """M-R1."""
        git(self.upstream, "branch", "feature", self.first)
        self.sync()
        self.assertEqual(refs(self.mirror)["refs/heads/feature"], self.first)

    def test_branche_avance_rapide(self):
        """M-R2."""
        third = commit_on(self.upstream, "third.c")
        output = self.sync_logged()
        self.assertEqual(refs(self.mirror)["refs/heads/master"], third)
        self.assertTrue(any("avance rapide" in line for line in output), output)

    def test_branche_identique(self):
        """M-R3: nothing sent, code 0, reported with -v only."""
        output = self.sync_logged()
        self.assertTrue(any("0 référence(s) envoyée(s), 0 signalement(s)" in line
                            for line in output), output)
        verbose = self.sync_logged("-v", level="DEBUG")
        self.assertTrue(any("identique" in line for line in verbose), verbose)

    def test_branche_reecrite_non_envoyee(self):
        """M-R4: a rewritten branch is not sent; the mirror keeps its commit."""
        git(self.upstream, "reset", "-q", "--hard", self.first)
        commit_on(self.upstream, "rewritten.c")
        output = self.sync_logged(expect=1)
        self.assertEqual(refs(self.mirror), self.before)
        self.assertTrue(any("master" in line and "non envoyée" in line for line in output),
                        output)

    def test_miroir_en_avance_non_envoye(self):
        """M-R4 (PA-67 E8): a mirror ahead of its upstream is reported too."""
        git(self.upstream, "reset", "-q", "--hard", self.first)
        self.sync(expect=1)
        self.assertEqual(refs(self.mirror), self.before)

    def test_branche_supprimee_conservee(self):
        """M-R5: kept in the mirror, reported at every pass (PA-67 E6)."""
        git(self.upstream, "branch", "-D", "dev")
        self.sync(expect=1)
        self.sync(expect=1)
        self.assertEqual(refs(self.mirror)["refs/heads/dev"], self.dev)

    def test_tag_nouveau(self):
        """M-R6: an annotated tag arrives as the same tag object."""
        git(self.upstream, "tag", "-a", "v2.0", "-m", "v2.0", self.second)
        self.sync()
        self.assertEqual(refs(self.mirror)["refs/tags/v2.0"], refs(self.upstream)["refs/tags/v2.0"])

    def test_tag_identique(self):
        """M-R7."""
        verbose = self.sync_logged("-v", level="DEBUG")
        self.assertTrue(any("v1.0" in line and "identique" in line for line in verbose), verbose)

    def test_tag_deplace_non_propage(self):
        """M-R8: a moved tag is reported with both commits, never propagated."""
        git(self.upstream, "tag", "-f", "-a", "v1.0", "-m", "moved", self.second)
        output = self.sync_logged(expect=1)
        self.assertEqual(refs(self.mirror), self.before)
        line = next(line for line in output if "v1.0" in line and "non propagé" in line)
        self.assertIn(self.first[:7], line)
        self.assertIn(self.second[:7], line)

    def test_tag_recree_meme_commit_non_propage(self):
        """M-R8 (PA-67 E7): another tag object on the same commit is a moved tag."""
        git(self.upstream, "tag", "-f", "-a", "v1.0", "-m", "recreated", self.first)
        output = self.sync_logged(expect=1)
        self.assertEqual(refs(self.mirror), self.before)
        self.assertTrue(any("même commit" in line for line in output), output)

    def test_tag_supprime_conserve(self):
        """M-R9."""
        git(self.upstream, "tag", "-d", "light")
        self.sync(expect=1)
        self.assertEqual(refs(self.mirror)["refs/tags/light"], self.first)

    def test_reference_refusee_signalee(self):
        """M-C4, M-K1: a reference the server refuses is reported; the others are sent."""
        hook = self.mirror / "hooks/update"
        hook.write_text('#!/bin/sh\ncase "$1" in refs/heads/feature) exit 1;; esac\nexit 0\n')
        hook.chmod(0o755)
        git(self.upstream, "branch", "feature", self.first)
        git(self.upstream, "tag", "v2.0", self.second)
        output = self.sync_logged(expect=1)
        self.assertNotIn("refs/heads/feature", refs(self.mirror))
        self.assertIn("refs/tags/v2.0", refs(self.mirror))
        self.assertTrue(any("feature" in line and "refus" in line for line in output), output)


class TestCodes(MirrorCase):
    def test_codes_de_retour_mirror_sync(self):
        """M-K1: 0 without report, 1 with a report or a declaration error, 2 on usage."""
        self.sync(expect=0)
        self.sync(expect=0)
        git(self.upstream, "tag", "-d", "light")
        self.sync(expect=1)
        self.sync("file://localhost/inconnu", expect=2)
        write(self.dot / ".scion.mirrors", "seul\n")
        self.sync(expect=1)

    def test_rien_supprime_ni_reecrit_dans_miroir(self):
        """M-K2: whatever the upstream does, no mirror reference is lost or rewritten."""
        self.sync()
        before = refs(self.mirror)
        git(self.upstream, "branch", "-D", "dev")
        git(self.upstream, "tag", "-d", "light")
        git(self.upstream, "tag", "-f", "-a", "v1.0", "-m", "moved", self.second)
        git(self.upstream, "reset", "-q", "--hard", self.first)
        commit_on(self.upstream, "rewritten.c")
        git(self.upstream, "branch", "feature")
        self.sync(expect=1)
        after = refs(self.mirror)
        for name, sha in before.items():
            self.assertEqual(after.get(name), sha, name)
        self.assertIn("refs/heads/feature", after)


class TestCompatibility(MirrorCase):
    def test_grafted_list_inchangee(self):
        """P-C1: mirror-sync writes nothing in the trunk."""
        before = (self.rootstock / "trunk/.scion.grafted.list").read_text()
        self.sync()
        self.assertEqual((self.rootstock / "trunk/.scion.grafted.list").read_text(), before)
        self.assertEqual(read_grafted(self.rootstock / "trunk/.scion.grafted.list"), {})


if __name__ == "__main__":
    unittest.main()
