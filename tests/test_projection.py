"""Projection of a repository without ``scion/`` (doc/projection-miroir.md, part A).

One case per rule of the specification, named after it. The third-party
repository is built by :func:`make_fixture.build_tiers`; nothing goes over the
network.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import make_fixture
from support import FixtureCase, oracle, run
from scion.model import read_grafted

HAL = "tiers/hal"
HAL_AT = "tiers@hal"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t", *args],
        cwd=repo, check=True, capture_output=True, text=True,
    ).stdout.strip()


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


class ProjectionCase(unittest.TestCase):
    """An empty rootstock, a third-party repository and a seed to fill."""

    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="scion-projection-")).resolve()
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.tiers = make_fixture.build_tiers(self.base / "repos/tiers")
        self.rootstock = self.base / "rootstock"
        (self.rootstock / "depots").mkdir(parents=True)
        (self.rootstock / ".scion.rootstock.signature").touch()
        (self.rootstock / "trunk").mkdir()
        (self.rootstock / "trunk/.scion.grafted.list").touch()
        self.trunk = self.rootstock / "trunk"
        self.seed_dir = self.base / "seed"
        self.dot = self.seed_dir / "scion/.scion"

    # -- seeds ---------------------------------------------------------------
    def declare(self, dot: Path, scions, projections: str) -> None:
        """``scions``: ``(shelf, name, version, location[, subpath])`` tuples."""
        write(dot / ".scion.sources.list",
              "".join("\t".join(scion) + "\n" for scion in scions))
        write(dot / ".scion.ramifications",
              "".join("\t".join(scion[:3]) + "\n" for scion in scions))
        write(dot / ".scion.projections", projections)

    def seed(self, projections: str, version: str = "v1.0", extra=(), location=None) -> None:
        hal = ("tiers", "hal", version, location or self.tiers.url)
        self.declare(self.dot, [hal, *extra], projections)

    def seed_add(self, expect: int = 0) -> str:
        code, _, err = run("seed-add", str(self.seed_dir), cwd=self.rootstock)
        self.assertEqual(code, expect, err)
        return err

    def graft(self, *args: str, expect: int = 0) -> str:
        code, _, err = run("graft", *args, cwd=self.rootstock)
        self.assertEqual(code, expect, err)
        return err

    def ready(self, projections: str, **kwargs) -> None:
        self.seed(projections, **kwargs)
        self.seed_add()
        self.graft()

    # -- porters -------------------------------------------------------------
    def porter(self, name: str, files: dict[str, str], scions, projections: str) -> Path:
        repo = self.base / "repos" / name
        for relative, text in files.items():
            write(repo / relative, text)
        self.declare(repo / "scion/.scion", scions, projections)
        make_fixture.make_repo(repo, {})
        return repo

    def hal_line(self, version: str = "v1.0"):
        return ("tiers", "hal", version, self.tiers.url)

    def url(self, repo: Path) -> str:
        return "file://localhost" + str(repo)

    # -- observations --------------------------------------------------------
    def clone(self, version: str = "v1.0") -> Path:
        return self.rootstock / "depots/tiers/hal" / version

    def links(self) -> dict[str, str]:
        """Trunk link -> real path of its target, relative to the test base."""
        found = {}
        for dirpath, _, filenames in os.walk(self.trunk):
            for name in filenames:
                path = Path(dirpath) / name
                if path.is_symlink():
                    target = Path(os.path.normpath(path.parent / os.readlink(path)))
                    found[str(path.relative_to(self.trunk))] = str(target.relative_to(self.base))
        return found

    def state(self) -> tuple:
        links, dirs = set(), set()
        for dirpath, dirnames, filenames in os.walk(self.trunk):
            for name in dirnames + filenames:
                path = Path(dirpath) / name
                relative = str(path.relative_to(self.trunk))
                if path.is_symlink():
                    links.add((relative, os.readlink(path)))
                elif path.is_dir():
                    dirs.add(relative)
        return frozenset(links), frozenset(dirs), (self.trunk / ".scion.grafted.list").read_text()

    def grafted_lines(self) -> list[list[str]]:
        return [line.split() for line in
                (self.trunk / ".scion.grafted.list").read_text().splitlines() if line]

    def grafted(self):
        return read_grafted(self.trunk / ".scion.grafted.list")


# ==========================================================================
# 1. compatibility
# ==========================================================================
class TestCompatibility(FixtureCase):
    def test_sans_projection_greffe_identique_0_5_4_0(self):
        self.seed_add()
        code, _, err = self.graft()
        self.assertEqual(code, 0, err)
        self.assertEqual(self.real_paths(), oracle())
        for line in (self.trunk / ".scion.grafted.list").read_text().splitlines():
            self.assertLessEqual(len(line.split()), 5)
        code, out, _ = run("rootstock-information", cwd=self.rootstock)
        self.assertEqual(code, 0)
        self.assertNotIn("projected", out)


class TestCompatibilityProjection(ProjectionCase):
    def test_liste_greffee_sans_sixieme_colonne_hors_porteur(self):
        self.ready("tiers hal Inc/* scion/inc/\n")
        line = next(f for f in self.grafted_lines() if f[1] == "hal")
        self.assertEqual(len(line), 5)

    def test_scion_dot_scion_sans_projections_ignore(self):
        repo = self.base / "repos/plain"
        write(repo / "scion/plain/p.c", "p\n")
        write(repo / "scion/.scion/.scion.sources.list", f"tiers\thal\tv1.0\t{self.tiers.url}\n")
        write(repo / "scion/.scion/.scion.ramifications", "tiers\thal\tv1.0\n")
        url = make_fixture.make_repo(repo, {})
        write(self.dot / ".scion.sources.list", f"local\tplain\tmaster\t{url}\n")
        write(self.dot / ".scion.ramifications", "local\tplain\tmaster\n")
        self.seed_add()
        self.graft()
        self.assertEqual(list(self.grafted()), ["local/plain"])
        self.assertFalse((self.rootstock / "depots/tiers").exists())


# ==========================================================================
# A.1, A.2 declaration and format
# ==========================================================================
class TestDeclaration(ProjectionCase):
    def test_cle_projetee_declaree_comme_scion(self):
        self.seed("tiers hal Inc/* scion/inc/\n")
        self.seed_add()
        entry = self.grafted()[HAL]
        self.assertEqual(entry.ref.version, "v1.0")
        self.assertEqual(entry.local_path, "depots/tiers/hal/v1.0")

    def test_cle_projetee_greffe_sans_repertoire_scion(self):
        self.ready("tiers hal Inc/* scion/inc/\n")
        self.assertEqual(self.links()["inc/a.h"], "rootstock/depots/tiers/hal/v1.0/Inc/a.h")

    def test_cle_projetee_chemin_dans_depot_refuse(self):
        write(self.dot / ".scion.sources.list", f"tiers\thal\tv1.0\t{self.tiers.url}\tsub\n")
        write(self.dot / ".scion.ramifications", "tiers\thal\tv1.0\n")
        write(self.dot / ".scion.projections", "tiers hal Inc/* scion/inc/\n")
        err = self.seed_add(expect=1)
        self.assertIn("chemin dans le dépôt", err)

    def test_projection_sans_ligne_de_sources_erreur(self):
        self.seed("tiers hal Inc/* scion/inc/\ntiers other Src/* scion/src/\n")
        err = self.seed_add(expect=1)
        self.assertIn(".scion.projections:2", err)
        self.assertIn("tiers/other", err)

    def test_ligne_projection_mal_formee_erreur_avec_numero(self):
        self.seed("tiers hal Inc/* scion/inc/\ntiers hal Inc/*\n"
                  "tiers hal Inc/* scion/inc/ extra\n")
        err = self.seed_add(expect=1)
        self.assertIn(".scion.projections:2", err)
        self.assertIn(".scion.projections:3", err)

    def test_fichier_tiers_a_blanc_projete_par_joker(self):
        self.ready("tiers hal docs/* scion/docs/\n")
        self.assertIn("docs/Add file.txt", self.links())


# ==========================================================================
# A.3 patterns
# ==========================================================================
class TestPatterns(ProjectionCase):
    def test_joker_dernier_segment(self):
        self.ready("tiers hal Inc/vendor_[ab]1*.h scion/inc/\n")
        self.assertEqual(set(self.links()), {"inc/vendor_a1.h", "inc/vendor_b1.h"})

    def test_joker_segment_interieur_refuse(self):
        self.seed("tiers hal In*/a.h scion/inc/\n")
        self.assertIn("dernier segment", self.seed_add(expect=1))

    def test_joker_point_initial(self):
        self.ready("tiers hal Inc/* scion/inc/\n")
        self.assertIn("inc/.keep", self.links())

    def test_double_etoile_dernier_segment_seulement(self):
        for pattern in ("Inc/**/a.h", "Src/x**"):
            with self.subTest(pattern=pattern):
                self.seed(f"tiers hal {pattern} scion/inc/\n")
                self.assertIn("**", self.seed_add(expect=1))

    def test_motif_point_point_refuse(self):
        for pattern in ("../x", "Inc/../a.h", "/Inc/a.h", "Inc//a.h"):
            with self.subTest(pattern=pattern):
                self.seed(f"tiers hal {pattern} scion/inc/\n")
                self.seed_add(expect=1)

    def test_non_suivi_jamais_projete(self):
        self.ready("tiers hal Inc/* scion/inc/\n")
        write(self.clone() / "Inc/untracked.h", "u\n")
        self.graft()
        self.assertNotIn("inc/untracked.h", self.links())

    def test_sous_module_ignore_par_recursif(self):
        self.ready("tiers hal Src/** scion/src/\n")
        self.assertEqual(set(self.links()), {"src/x.c", "src/deep/y.c"})
        self.seed("tiers hal Src/mod scion/src/\n")
        self.assertIn("sous-module", self.graft(expect=1))

    def test_lien_committe_projete_comme_feuille(self):
        self.ready("tiers hal Inc/* scion/inc/\n")
        link = self.trunk / "inc/link.h"
        target = Path(os.path.normpath(link.parent / os.readlink(link)))
        self.assertEqual(target, self.clone() / "Inc/link.h")
        self.assertTrue(target.is_symlink())

    def test_forme_fichier_sur_repertoire_refusee(self):
        self.seed("tiers hal Inc/sub scion/inc/\n")
        self.seed_add()
        self.assertIn("Inc/sub/*", self.graft(expect=1))


# ==========================================================================
# A.4 destinations
# ==========================================================================
class TestDestinations(ProjectionCase):
    def test_destination_sans_prefixe_scion_refusee(self):
        self.seed("tiers hal Inc/* inc/\n")
        self.assertIn("scion/", self.seed_add(expect=1))

    def test_renommage_de_base_repertoire(self):
        self.ready("tiers hal Inc/* scion/include/\ntiers hal Inc/** scion/x/\n")
        links = self.links()
        self.assertIn("include/a.h", links)
        self.assertNotIn("include/sub/c.h", links)
        self.assertEqual(links["x/sub/c.h"], "rootstock/depots/tiers/hal/v1.0/Inc/sub/c.h")

    def test_renommage_de_fichier(self):
        self.ready("tiers hal README.md scion/doc/LISEZMOI.md\n")
        self.assertEqual(self.links(), {"doc/LISEZMOI.md":
                                        "rootstock/depots/tiers/hal/v1.0/README.md"})

    def test_destination_fichier_pour_recursif_refusee(self):
        self.seed("tiers hal Inc/** scion/inc\n")
        self.assertIn("/", self.seed_add(expect=1))

    def test_destination_segment_dot_scion_refusee(self):
        for destination in ("scion/.scion/", "scion/a/./b/", "scion/a//b/"):
            with self.subTest(destination=destination):
                self.seed(f"tiers hal Inc/* {destination}\n")
                self.seed_add(expect=1)
        self.seed("tiers hal cfg/** scion/cfg/\n")
        self.seed_add()
        self.assertIn(".scion", self.graft(expect=1))

    def test_destination_liste_greffee_refusee(self):
        self.seed("tiers hal README.md scion/.scion.grafted.list\n")
        self.assertIn(".scion.grafted.list", self.seed_add(expect=1))


# ==========================================================================
# A.5, A.6 exclusions and resolution
# ==========================================================================
class TestResolution(ProjectionCase):
    def test_exclusion_toutes_inclusions_ordre_indifferent(self):
        self.ready("tiers hal !Inc/b.h\ntiers hal Inc/* scion/inc/\n"
                   "tiers hal Inc/b.h scion/other/\ntiers hal Inc/a.h scion/other/\n")
        links = self.links()
        self.assertNotIn("inc/b.h", links)
        self.assertEqual(set(k for k in links if k.startswith("other/")), {"other/a.h"})

    def test_exclusion_porte_sur_la_source(self):
        self.ready("tiers hal Inc/* scion/inc/\ntiers hal !Inc/a.h\n")
        self.assertNotIn("inc/a.h", self.links())
        self.seed("tiers hal Inc/* scion/inc/\ntiers hal !inc/b.h\n")
        self.assertIn("exclusion", self.graft(expect=1))

    def test_inclusion_sans_correspondance_erreur_trunk_retabli(self):
        self.ready("tiers hal Inc/* scion/inc/\n")
        before = self.state()
        self.seed("tiers hal Inc/* scion/inc/\ntiers hal Nope/* scion/nope/\n")
        err = self.graft(expect=1)
        self.assertIn("aucun fichier", err)
        self.assertEqual(self.state(), before)

    def test_exclusion_sans_correspondance_erreur(self):
        self.seed("tiers hal Inc/* scion/inc/\ntiers hal !Src/x.c\n")
        self.seed_add()
        self.assertIn("exclusion", self.graft(expect=1))

    def test_meme_source_meme_destination_un_lien(self):
        self.ready("tiers hal Inc/* scion/inc/\ntiers hal Inc/a.h scion/inc/\n")
        self.assertIn("inc/a.h", self.links())

    def test_deux_sources_meme_destination_erreur(self):
        self.seed("tiers hal Inc/a.h scion/x.h\ntiers hal Inc/b.h scion/x.h\n")
        self.seed_add()
        err = self.graft(expect=1)
        self.assertIn(".scion.projections:1", err)
        self.assertIn(".scion.projections:2", err)

    def test_une_source_deux_destinations(self):
        self.ready("tiers hal Inc/a.h scion/one/\ntiers hal Inc/a.h scion/two/\n")
        links = self.links()
        self.assertEqual(links["one/a.h"], links["two/a.h"])

    def test_fichier_projete_contre_repertoire_erreur(self):
        self.seed("tiers hal README.md scion/inc\ntiers hal Inc/* scion/inc/\n")
        self.seed_add()
        self.assertIn("à la fois un fichier et un répertoire", self.graft(expect=1))


# ==========================================================================
# A.7 case
# ==========================================================================
class TestCasse(ProjectionCase):
    def plain(self, files: dict[str, str]):
        url = make_fixture.make_repo(self.base / "repos/plain", files)
        return ("local", "plain", "master", url)

    def test_motif_sensible_a_la_casse(self):
        self.seed("tiers hal inc/a.h scion/inc/\n")
        self.seed_add()
        self.assertIn("aucun fichier", self.graft(expect=1))

    def test_collision_de_casse_projection_contre_scion_erreur(self):
        self.seed("tiers hal Inc/a.h scion/inc/\n", extra=[self.plain({"scion/Inc/z.h": "z\n"})])
        self.seed_add()
        err = self.graft(expect=1)
        self.assertIn("casse", err)
        self.assertEqual(self.links(), {})

    def test_collision_de_casse_sur_repertoire(self):
        self.seed("tiers hal Inc/a.h scion/inc/A.h\n",
                  extra=[self.plain({"scion/inc/a.h": "z\n"})])
        self.seed_add()
        self.assertIn("casse", self.graft(expect=1))


# ==========================================================================
# A.8 version, clone, state of the clone
# ==========================================================================
class TestVersions(ProjectionCase):
    def test_version_tag(self):
        self.ready("tiers hal Inc/* scion/inc/\n")
        self.assertEqual(git(self.clone(), "rev-parse", "HEAD"), self.tiers.first)

    def test_version_commit(self):
        self.ready("tiers hal Src/* scion/src/\n", version=self.tiers.dev)
        clone = self.clone(self.tiers.dev)
        self.assertEqual(git(clone, "rev-parse", "HEAD"), self.tiers.dev)
        self.assertEqual(git(clone, "branch", "--show-current"), "")
        self.assertIn("src/dev.c", self.links())

    def test_version_branche_refusee(self):
        self.seed("tiers hal Inc/* scion/inc/\n", version="dev")
        self.assertIn("branche", self.seed_add(expect=1))

    def test_version_etoile_et_point_d_interrogation_refusees(self):
        for version in ("*", "?"):
            with self.subTest(version=version):
                self.seed("tiers hal Inc/* scion/inc/\n", version=version)
                self.assertIn("refusée", self.seed_add(expect=1))

    def test_clone_partiel_blob_none_head_detache(self):
        self.seed("tiers hal Inc/* scion/inc/\n")
        self.seed_add()
        clone = self.clone()
        self.assertEqual(git(clone, "config", "remote.origin.partialclonefilter"), "blob:none")
        self.assertEqual(git(clone, "branch", "--show-current"), "")

    def test_meme_prefixe_meme_version_clone_partage(self):
        sources = (f"tiers\thal::inc\tv1.0\t{self.tiers.url}\n"
                   f"tiers\thal::src\tv1.0\t{self.tiers.url}\n")
        write(self.dot / ".scion.sources.list", sources)
        write(self.dot / ".scion.ramifications", "tiers\thal::inc\tv1.0\ntiers\thal::src\tv1.0\n")
        write(self.dot / ".scion.projections",
              "tiers hal::inc Inc/* scion/inc/\ntiers hal::src Src/* scion/src/\n")
        self.seed_add()
        self.graft()
        self.assertEqual(sorted(p.name for p in (self.rootstock / "depots/tiers/hal").iterdir()),
                         ["v1.0"])
        self.graft("--scion", "tiers@hal::inc")
        self.assertIn("src/x.c", self.links())
        code, _, err = run("graft-remove", "tiers@hal::inc", cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.assertIn("src/x.c", self.links())
        self.assertNotIn("inc/a.h", self.links())

    def test_emplacement_local_git_utilise_tel_quel(self):
        location = str(self.tiers.path)
        self.ready("tiers hal Src/* scion/src/\n", version=self.tiers.second, location=location)
        self.assertEqual(self.links()["src/z.c"], "repos/tiers/Src/z.c")
        self.assertFalse((self.rootstock / "depots/tiers").exists())

    def test_emplacement_local_hors_git_refuse(self):
        plain = self.base / "plain"
        write(plain / "Inc/a.h", "a\n")
        self.seed("tiers hal Inc/* scion/inc/\n", version=self.tiers.first, location=str(plain))
        self.assertIn("dépôt git", self.seed_add(expect=1))

    def test_tag_deplace_arrete_graft_update(self):
        self.ready("tiers hal Inc/* scion/inc/\n")
        git(self.tiers.path, "tag", "-f", "-a", "v1.0", "-m", "moved", self.tiers.second)
        before = self.state()
        code, _, err = run("graft-update", cwd=self.rootstock)
        self.assertEqual(code, 1)
        self.assertIn("déplacé", err)
        self.assertEqual(self.state(), before)

    def test_commit_absent_fetch_puis_erreur(self):
        early = self.base / "early"
        git(self.base, "clone", "-q", self.tiers.url, str(early))
        write(self.tiers.path / "Src/late.c", "late\n")
        make_fixture.commit_all(self.tiers.path, "late")
        late = git(self.tiers.path, "rev-parse", "HEAD")
        self.ready("tiers hal Inc/* scion/inc/\n")
        for version, message in ((late, "checkout --detach"), ("d" * 40, "absent")):
            with self.subTest(version=version):
                clone = self.clone(version)
                shutil.copytree(early, clone, symlinks=True)
                self.seed("tiers hal Inc/* scion/inc/\n", version=version)
                code, _, err = run("graft-update", cwd=self.rootstock)
                self.assertEqual(code, 1)
                self.assertIn(message, err)
        self.assertTrue(subprocess.run(["git", "cat-file", "-e", late], cwd=self.clone(late))
                        .returncode == 0)

    def test_changement_de_version_nouveau_clone(self):
        self.ready("tiers hal Src/* scion/src/\n")
        self.seed("tiers hal Src/* scion/src/\n", version="v2.0")
        code, _, err = run("graft-update", cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.assertTrue(self.clone("v1.0").is_dir())
        self.assertEqual(self.links()["src/z.c"], "rootstock/depots/tiers/hal/v2.0/Src/z.c")
        code, _, err = run("graft-remove", "--purge", HAL_AT, cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.assertTrue(self.clone("v1.0").is_dir())

    def test_version_declaree_remplace_toujours(self):
        self.ready("tiers hal Src/* scion/src/\n", version="v2.0")
        self.seed("tiers hal Src/* scion/src/\n", version="v1.0")
        code, _, err = run("graft-update", cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.grafted()[HAL].ref.version, "v1.0")
        self.assertNotIn("src/z.c", self.links())

    def test_clone_modifie_greffe_refusee(self):
        self.ready("tiers hal Inc/* scion/inc/\n")
        before = self.state()
        write(self.clone() / "Inc/a.h", "changed\n")
        err = self.graft(expect=1)
        self.assertIn("Inc/a.h", err)
        self.assertEqual(self.state(), before)

    def test_clone_hors_commit_refuse(self):
        self.ready("tiers hal Inc/* scion/inc/\n")
        git(self.clone(), "checkout", "-q", "--detach", self.tiers.second)
        self.assertIn("checkout --detach v1.0", self.graft(expect=1))

    def test_non_suivi_ne_bloque_pas(self):
        self.ready("tiers hal Inc/* scion/inc/\n")
        write(self.clone() / "Inc/new.h", "n\n")
        self.graft()


# ==========================================================================
# A.9 carrier scions
# ==========================================================================
class CarrierCase(ProjectionCase):
    """A seed whose scions carry projections."""

    def carrier(self, name="family", files=None, projections="tiers hal Inc/* scion/inc/\n",
                scions=None):
        repo = self.porter(name, files or {f"scion/{name}/f.c": "f\n"},
                           scions or [self.hal_line()], projections)
        return repo

    def seed_with(self, *repos: Path) -> None:
        lines = [("own", repo.name, "master", self.url(repo))
                 for repo in repos]
        write(self.dot / ".scion.sources.list", "".join("\t".join(f) + "\n" for f in lines))
        write(self.dot / ".scion.ramifications", "".join("\t".join(f[:3]) + "\n" for f in lines))


class TestCarriers(CarrierCase):
    def test_porteur_lu_dot_scion_non_greffe(self):
        self.seed_with(self.carrier())
        self.seed_add()
        self.graft()
        links = self.links()
        self.assertIn("family/f.c", links)
        self.assertIn("inc/a.h", links)
        self.assertFalse(any(".scion" in Path(k).parts for k in links))

    def test_porteur_scion_ordinaire_refuse(self):
        other = ("own", "other", "master", self.tiers.url)
        self.seed_with(self.carrier(scions=[self.hal_line(), other]))
        self.assertIn("porteur", self.seed_add(expect=1))

    def test_porteur_sixieme_colonne(self):
        self.seed_with(self.carrier())
        self.seed_add()
        line = next(f for f in self.grafted_lines() if f[1] == "hal")
        self.assertEqual(line[4], str(self.dot))
        self.assertEqual(line[5], "depots/own/family/master/scion/.scion")

    def test_ordre_des_porteurs(self):
        first = self.carrier("first", projections="tiers one Inc/a.h scion/one/\n",
                             scions=[("tiers", "one", "v1.0", self.tiers.url)])
        second = self.carrier("second", projections="tiers two Inc/b.h scion/two/\n",
                              scions=[("tiers", "two", "v1.0", self.tiers.url)])
        self.seed_with(second, first)
        self.seed_add()
        self.assertEqual(list(self.grafted()),
                         ["own/second", "own/first", "tiers/two", "tiers/one"])

    def test_double_declaration_identique_admise(self):
        self.seed_with(self.carrier())
        hal = self.hal_line()
        family = ("own", "family", "master", self.url(self.base / "repos/family"))
        self.declare(self.dot, [family, hal], "tiers hal Inc/* scion/inc/\n")
        self.seed_add()
        self.graft()
        line = next(f for f in self.grafted_lines() if f[1] == "hal")
        self.assertEqual(len(line), 5)

    def test_double_declaration_differente_erreur(self):
        self.seed_with(self.carrier())
        family = ("own", "family", "master", self.url(self.base / "repos/family"))
        self.declare(self.dot, [family, self.hal_line()], "tiers hal Src/* scion/src/\n")
        self.assertIn("différemment", self.seed_add(expect=1))

    def test_porteur_avance_projection_suit(self):
        repo = self.carrier()
        self.seed_with(repo)
        self.seed_add()
        self.graft()
        self.declare(repo / "scion/.scion", [self.hal_line("v2.0")], "tiers hal Src/* scion/src/\n")
        make_fixture.commit_all(repo)
        code, _, err = run("graft-update", cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.links()["src/z.c"], "rootstock/depots/tiers/hal/v2.0/Src/z.c")
        self.assertNotIn("inc/a.h", self.links())

    def test_cle_que_le_porteur_ne_declare_plus_retiree(self):
        repo = self.carrier()
        self.seed_with(repo)
        self.seed_add()
        self.graft()
        shutil.rmtree(repo / "scion/.scion")
        make_fixture.commit_all(repo)
        code, _, err = run("graft-update", cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.assertNotIn(HAL, self.grafted())
        self.assertNotIn("inc/a.h", self.links())
        self.assertTrue(self.clone().is_dir())

    def test_graft_remove_porteur_retire_ses_projections(self):
        self.seed_with(self.carrier())
        self.seed_add()
        self.graft()
        with self.assertLogs("scion.graft", level="INFO") as logs:
            code, _, err = run("graft-remove", "own@family", cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.assertTrue(any(HAL in line for line in logs.output))
        self.assertEqual(self.links(), {})
        self.assertEqual(list(self.grafted()), [])
        self.assertFalse((self.trunk / "inc").exists())


# ==========================================================================
# A.10 graft, ownership, removal
# ==========================================================================
class TestGraftOwnership(CarrierCase):
    def test_liens_relatifs_vers_clone_tiers_repertoires_partages(self):
        self.seed_with(self.carrier(files={"scion/inc/local.h": "l\n"}))
        self.seed_add()
        self.graft()
        self.assertFalse(os.path.isabs(os.readlink(self.trunk / "inc/a.h")))
        self.assertTrue((self.trunk / "inc").is_dir() and not (self.trunk / "inc").is_symlink())
        self.assertIn("inc/local.h", self.links())

    def test_conflit_projection_contre_scion(self):
        self.seed_with(self.carrier(files={"scion/inc/a.h": "mine\n"}))
        self.seed_add()
        err = self.graft(expect=1)
        self.assertIn("own/family", err)
        self.assertIn(HAL, err)
        self.assertEqual(self.links(), {})

    def test_remplacement_local_par_exclusion(self):
        self.seed_with(self.carrier(files={"scion/inc/a.h": "mine\n"},
                                    projections="tiers hal Inc/* scion/inc/\ntiers hal !Inc/a.h\n"))
        self.seed_add()
        self.graft()
        self.assertEqual(self.links()["inc/a.h"],
                         "rootstock/depots/own/family/master/scion/inc/a.h")

    def test_proprietaire_repertoire_projete(self):
        repo = self.carrier()
        self.seed_with(repo)
        self.seed_add()
        self.graft()
        clone = self.rootstock / "depots/own/family/master"
        write(clone / "scion/inc", "a file\n")
        err = self.graft("--scion", "own@family", expect=1)
        self.assertIn(f"déjà fourni par « {HAL} »", err)

    def test_elagage_apres_graft_remove_projection(self):
        self.seed_with(self.carrier())
        self.seed_add()
        self.graft()
        code, _, err = run("graft-remove", HAL_AT, cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.assertFalse((self.trunk / "inc").exists())
        self.assertIn("family/f.c", self.links())

    def test_filtre_ignore_sans_effet_sur_projection(self):
        self.seed("tiers hal Inc/* scion/inc/\n")
        self.seed_add()
        clone = self.clone()
        write(clone / ".git/info/exclude", "*.h\n*.tmp\n")
        write(clone / "Inc/scratch.tmp", "t\n")
        self.graft()
        links = self.links()
        self.assertIn("inc/a.h", links)
        self.assertNotIn("inc/scratch.tmp", links)

    def test_graft_scion_cle_projetee_seule(self):
        repo = self.carrier()
        self.seed_with(repo)
        self.seed_add()
        self.graft()
        family = os.lstat(self.trunk / "family/f.c").st_ino
        clone = self.rootstock / "depots/own/family/master"
        write(clone / "scion/.scion/.scion.projections",
              "tiers hal Inc/* scion/inc/\ntiers hal README.md scion/doc/\n")
        self.graft("--scion", HAL_AT)
        self.assertIn("doc/README.md", self.links())
        self.assertEqual(os.lstat(self.trunk / "family/f.c").st_ino, family)


# ==========================================================================
# A.11, A.12 commands and messages
# ==========================================================================
class TestCommands(ProjectionCase):
    def test_seed_add_clone_projections(self):
        self.seed("tiers hal Inc/* scion/inc/\n")
        self.seed_add()
        self.assertTrue((self.clone() / ".git").exists())
        self.assertTrue((self.clone() / "Inc/a.h").exists())

    def test_rootstock_information_compte_projections(self):
        self.ready("tiers hal Inc/* scion/inc/\n")
        code, out, _ = run("rootstock-information", cwd=self.rootstock)
        self.assertEqual(code, 0)
        self.assertIn("scions grafted: 1", out)
        self.assertIn("scions projected: 1", out)

    def test_git_key_cle_projetee(self):
        self.ready("tiers hal Inc/* scion/inc/\n")
        code, out, err = run("git", "--key", HAL_AT, "--args", "rev-parse HEAD",
                             cwd=self.rootstock)
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), self.tiers.first)

    def test_messages_citent_fichier_et_ligne(self):
        self.seed("tiers hal Inc/* scion/inc/\ntiers hal Nope/a.h scion/n/\n")
        self.seed_add()
        err = self.graft(expect=1)
        self.assertIn(f"{self.dot}/.scion.projections:2", err)
        self.assertIn(HAL, err)
        self.assertIn("Nope/a.h", err)

    def test_verbose_liste_par_ligne(self):
        self.seed("tiers hal Inc/* scion/inc/\ntiers hal !Inc/b.h\n")
        self.seed_add()
        with self.assertLogs("scion.projection", level="DEBUG") as logs:
            self.graft("-v")
        self.assertTrue(any("fichier(s)" in line and "Inc/*" in line for line in logs.output))
        self.assertTrue(any("exclu Inc/b.h" in line for line in logs.output))


if __name__ == "__main__":
    unittest.main()
