"""Build a self-contained scion fixture: no network, no pytest, no leftovers.

The fixture reproduces the cases that matter for the rewrite:

* two scions carved out of the *same* repository through different subpaths
  (``core::kernel`` and ``core::lib``), both grafting into a shared ``sys/`` root
  -- this is what made the old directory-level graft write into the clones;
* a scion whose ``scion/`` sits at the root of the repository, i.e. with no
  "path in repository" column, holding a *versioned* symlink and a deep tree;
* a local, unversioned scion (version ``*``) given as a path relative to the
  rootstock;
* the same scion declared twice, in a seed of its own, so that version ``?``
  has something to choose from;
* a second seed adding a scion that collides with an already grafted file.

Repositories are served over ``file://localhost/...`` so that ``urlparse`` sees a
netloc (they are remote as far as scion is concerned) while git still clones
them from disk.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

SIGNATURE = ".scion.rootstock.signature"
GRAFTED_LIST = ".scion.grafted.list"
RAMIFICATIONS = ".scion.ramifications"
SOURCES_LIST = ".scion.sources.list"


@dataclass(frozen=True)
class Fixture:
    base: Path
    rootstock: Path
    repos: Path
    seed: Path
    seed_assets: Path
    seed_conflict: Path

    @property
    def trunk(self) -> Path:
        return self.rootstock / "trunk"

    @property
    def depots(self) -> Path:
        return self.rootstock / "depots"

    def clones(self) -> list[Path]:
        """Every git clone under depots/, deepest first."""
        return sorted(p.parent for p in self.depots.rglob(".git"))


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _make_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q", "-b", "master")
    _git(path, "config", "user.email", "fixture@example.invalid")
    _git(path, "config", "user.name", "scion fixture")
    _git(path, "add", "-A")
    _git(path, "commit", "-qm", "fixture")


def _url(repo: Path) -> str:
    return "file://localhost" + str(repo.resolve())


def build(base: Path) -> Fixture:
    base = Path(base)
    repos = base / "repos"

    # --- alpha: one repository, two scions, shared sys/ root ----------------
    alpha = repos / "alpha"
    _write(alpha / "kernel/scion/sys/root/src/kernel/core/kernel.c", "/* kernel */\n")
    _write(alpha / "kernel/scion/sys/root/include/kernel.h", "/* kernel.h */\n")
    # .scion/ inside a scion must never be grafted
    _write(alpha / "kernel/scion/.scion/ignored.txt", "not grafted\n")
    _write(alpha / "lib/scion/sys/root/src/lib/libc.c", "/* libc */\n")
    _write(alpha / "lib/scion/sys/root/include/libc.h", "/* libc.h */\n")
    _make_repo(alpha)

    # --- beta: scion/ at the repository root, no subpath column -------------
    beta = repos / "beta"
    _write(beta / "scion/tools/bin/tool.sh", "#!/bin/sh\necho tool\n")
    _write(beta / "scion/tools/doc/deep/a/b/c/readme.txt", "deep\n")
    (beta / "scion/tools/bin/tool-link.sh").symlink_to("tool.sh")
    _make_repo(beta)

    # --- gamma: collides with alpha's kernel scion --------------------------
    gamma = repos / "gamma"
    _write(gamma / "scion/sys/root/include/kernel.h", "/* duplicate */\n")
    _make_repo(gamma)

    # --- seeds --------------------------------------------------------------
    nominal_sources = f"""\
#shelf\tscion\t\tversion\tdepot location\t\t\tscion location in depot
#
alpha\tcore::kernel\tmaster\t{_url(alpha)}\tkernel
alpha\tcore::lib\tmaster\t{_url(alpha)}\tlib
#
beta\ttools::bin\tmaster\t{_url(beta)}
#
local\tbuilding\t*\t\tdepots/generation/building
truncated\tline\twithout\t
"""
    nominal_ramifications = """\
alpha \tcore::kernel    \t\tmaster
alpha  core::lib \t\t\tmaster
beta   tools::bin\t\t\tmaster
local  building \t\t\t*
"""
    seed = base / "seed"
    _write(seed / "scion/.scion" / SOURCES_LIST, nominal_sources)
    _write(seed / "scion/.scion" / RAMIFICATIONS, nominal_ramifications)

    # a seed of its own for version "?": the old tool cannot resolve it, so it
    # must stay out of the graft oracle.
    seed_assets = base / "seed-assets"
    _write(
        seed_assets / "scion/.scion" / SOURCES_LIST,
        "local\tgen::assets\t1.0\t\tdepots/generation/assets/1.0\n"
        "local\tgen::assets\t1.2\t\tdepots/generation/assets/1.2\n",
    )
    _write(seed_assets / "scion/.scion" / RAMIFICATIONS, "local\tgen::assets\t?\n")

    seed_conflict = base / "seed-conflict"
    _write(
        seed_conflict / "scion/.scion" / SOURCES_LIST,
        f"gamma\tx::dup\tmaster\t{_url(gamma)}\n",
    )
    _write(seed_conflict / "scion/.scion" / RAMIFICATIONS, "gamma\tx::dup\tmaster\n")

    # --- rootstock ----------------------------------------------------------
    rootstock = base / "rootstock"
    (rootstock / "depots").mkdir(parents=True, exist_ok=True)
    (rootstock / SIGNATURE).touch()
    (rootstock / "trunk").mkdir(exist_ok=True)
    (rootstock / "trunk" / GRAFTED_LIST).touch()

    building = rootstock / "depots/generation/building/scion/building"
    for sub in ("projects", "staging/lib", "output"):
        (building / sub).mkdir(parents=True, exist_ok=True)

    assets = rootstock / "depots/generation/assets"
    _write(assets / "1.0/scion/assets/theme.txt", "assets 1.0\n")
    _write(assets / "1.2/scion/assets/theme.txt", "assets 1.2\n")

    return Fixture(
        base=base,
        rootstock=rootstock,
        repos=repos,
        seed=seed,
        seed_assets=seed_assets,
        seed_conflict=seed_conflict,
    )


def real_paths(trunk: Path, base: Path) -> set[str]:
    """Every file reachable from the trunk, resolved to its real location.

    Directories are left out on purpose: the old tool made them symlinks and the
    new one makes them real, which is exactly the difference we do *not* want to
    assert on. Results are relative to ``base`` so that two fixtures built in
    different temporary directories -- or a rootstock that has been moved --
    compare equal.
    """
    base = Path(base).resolve()
    found: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(trunk, followlinks=True):
        dirnames.sort()
        for name in filenames:
            if name == GRAFTED_LIST:
                continue
            found.add(str((Path(dirpath) / name).resolve().relative_to(base)))
    return found
