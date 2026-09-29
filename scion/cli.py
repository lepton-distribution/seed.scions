"""Command line interface. The only module that prints and that exits."""

from __future__ import annotations

import argparse
import logging
import shlex
import sys
from pathlib import Path

from . import __version__, gitops, graft as graft_ops, rootstock as rootstock_ops
from .errors import ScionError
from .model import read_grafted
from .rootstock import DEFAULT_TRUNK, HIDDEN_DIR, STEM_DIR

log = logging.getLogger("scion")


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _rootstock(args) -> rootstock_ops.Rootstock:
    return rootstock_ops.discover(explicit=args.rootstock_path, trunk=args.trunk)


def _current_seed_root() -> str | None:
    """The enclosing ``scion/`` directory, so that --seed can be omitted there."""
    parts = Path.cwd().resolve().parts
    if STEM_DIR not in parts:
        return None
    return str(Path(*parts[: parts.index(STEM_DIR) + 1]))


def find_dot_scion(path) -> Path:
    """Locate the ``.scion/`` directory of a seed, shallowest first."""
    root = Path(path).resolve()
    if not root.is_dir():
        raise ScionError(f"seed introuvable : {root}")
    candidates = sorted(
        (p for p in root.rglob(HIDDEN_DIR) if p.is_dir()),
        key=lambda p: (len(p.parts), str(p)),
    )
    if not candidates:
        raise ScionError(f"aucun répertoire {HIDDEN_DIR}/ trouvé sous {root}")
    return candidates[0]


def _seed_dot_scion(args) -> Path:
    seed = args.seed or _current_seed_root()
    if not seed:
        raise ScionError(
            f"--seed est requis hors d'un répertoire {STEM_DIR}/ de seed"
        )
    return find_dot_scion(seed)


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------
def cmd_version(args) -> int:
    print(f"python version: {sys.version}")
    print(f"scion version: {__version__}")
    return 0


def cmd_rootstock_information(args) -> int:
    rootstock = _rootstock(args)
    print(f"rootstock: {rootstock.path}")
    print(f"trunk: {rootstock.trunk_name}")
    print(f"scions grafted: {len(read_grafted(rootstock.grafted_list))}")
    return 0


def cmd_rootstock_install(args) -> int:
    rootstock = rootstock_ops.install(Path.cwd(), args.trunk or DEFAULT_TRUNK)
    log.info("rootstock installé dans %s (trunk : %s)", rootstock.path, rootstock.trunk_name)
    return 0


def cmd_seed_add(args) -> int:
    if not args.seed_url:
        raise ScionError("seed-add attend l'URL ou le chemin d'un seed")
    rootstock = _rootstock(args)
    local = _clone_seed(rootstock, args.seed_url, args.version, args.single_branch)
    graft_ops.sync(rootstock, find_dot_scion(local), args.single_branch, update=True)
    return 0


def _clone_seed(rootstock, seed_url: str, version: str, single_branch: bool) -> Path:
    if not graft_ops.is_remote(seed_url):
        return Path(seed_url).resolve()
    name = Path(seed_url.rstrip("/")).stem
    local = rootstock.depots / name / version
    if (local / ".git").exists():
        gitops.pull(local)
    else:
        gitops.clone(seed_url, local, version, single_branch)
    return local


def cmd_seed_clone(args) -> int:
    rootstock = _rootstock(args)
    graft_ops.sync(rootstock, _seed_dot_scion(args), args.single_branch, update=False)
    return 0


def cmd_seed_update(args) -> int:
    rootstock = _rootstock(args)
    graft_ops.sync(rootstock, _seed_dot_scion(args), False, update=True)
    return 0


def cmd_graft(args) -> int:
    rootstock = _rootstock(args)
    graft_ops.ungraft(rootstock, force=args.force)
    graft_ops.graft(rootstock)
    return 0


def cmd_ungraft(args) -> int:
    graft_ops.ungraft(_rootstock(args), force=args.force)
    return 0


def cmd_graft_clean(args) -> int:
    rootstock = _rootstock(args)
    graft_ops.ungraft(rootstock, force=args.force)
    graft_ops.clean(rootstock)
    return 0


def cmd_graft_update(args) -> int:
    rootstock = _rootstock(args)
    graft_ops.ungraft(rootstock, force=args.force)
    for seed in graft_ops.seeds(rootstock):
        graft_ops.sync(rootstock, rootstock.resolve(seed), False, update=True)
    graft_ops.graft(rootstock)
    return 0


def cmd_git(args) -> int:
    rootstock = _rootstock(args)
    key = args.key.replace("@", "/", 1)
    entry = read_grafted(rootstock.grafted_list).get(key)
    if entry is None:
        raise ScionError(f"scion « {args.key} » absent de {rootstock.grafted_list}")
    gitops.run(shlex.split(args.args), cwd=rootstock.resolve(entry.local_path))
    return 0


COMMANDS = {
    "version": cmd_version,
    "rootstock-information": cmd_rootstock_information,
    "rootstock-install": cmd_rootstock_install,
    "seed-add": cmd_seed_add,
    "seed-clone": cmd_seed_clone,
    "seed-update": cmd_seed_update,
    "graft": cmd_graft,
    "ungraft": cmd_ungraft,
    "graft-clean": cmd_graft_clean,
    "graft-update": cmd_graft_update,
    "git": cmd_git,
}


# --------------------------------------------------------------------------
# parser
# --------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-v", "--verbose", action="store_true", help="journal détaillé")
    common.add_argument(
        "--trunk", default=None,
        help="nom du répertoire trunk (par défaut celui qui porte la liste greffée)",
    )
    located = argparse.ArgumentParser(add_help=False, parents=[common])
    located.add_argument(
        "rootstock_path", nargs="?", default=None,
        help="rootstock à utiliser (par défaut, le premier trouvé en remontant)",
    )

    parser = argparse.ArgumentParser(
        prog="scion",
        description="Compose un arbre de sources unique (le trunk d'un rootstock) "
                    "en superposant des sous-arbres (scions) issus de plusieurs dépôts.",
    )
    sub = parser.add_subparsers(dest="command", metavar="commande")

    sub.add_parser("version", parents=[common], help="affiche les versions")
    sub.add_parser("rootstock-information", parents=[located],
                   help="affiche le rootstock courant et son trunk")
    sub.add_parser("rootstock-install", parents=[common],
                   help="initialise le répertoire courant (vide) en rootstock")

    add = sub.add_parser("seed-add", parents=[common],
                         help="ajoute un seed au rootstock et cloner ses scions")
    add.add_argument("--version", default="master", help="version (branche) du seed")
    _single_branch(add)
    add.add_argument("seed_url", nargs="?", help="URL ou chemin du dépôt de seed")
    add.add_argument("rootstock_path", nargs="?", default=None)

    clone = sub.add_parser("seed-clone", parents=[located],
                           help="clone les scions d'un seed déjà présent")
    clone.add_argument("--seed", default=None, help="chemin du seed")
    _single_branch(clone)

    update = sub.add_parser("seed-update", parents=[located],
                            help="met à jour les clones des scions d'un seed")
    update.add_argument("--seed", default=None, help="chemin du seed")

    graft = sub.add_parser("graft", parents=[located],
                           help="greffe sur le trunk tous les scions de la liste greffée")
    _force(graft)
    ungraft = sub.add_parser("ungraft", parents=[located], help="vide le trunk")
    _force(ungraft)
    clean = sub.add_parser("graft-clean", parents=[located],
                           help="vide le trunk et oublie la liste greffée")
    _force(clean)
    graft_update = sub.add_parser(
        "graft-update", parents=[located],
        help="met à jour tous les seeds de la liste greffée puis regreffe",
    )
    _force(graft_update)

    git = sub.add_parser("git", parents=[located],
                         help="exécute une commande git dans le dépôt d'un scion")
    git.add_argument("--key", required=True, metavar="shelf@prefix::suffix")
    git.add_argument("--args", required=True, metavar='"status --short"')
    return parser


def _single_branch(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--single_branch", "--single-branch", dest="single_branch", action="store_true",
        help="ne récupérer que la branche demandée",
    )


def _force(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--force", action="store_true",
        help="dégreffer même si le trunk contient des fichiers qui ne sont pas des liens",
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if getattr(args, "verbose", False) else logging.INFO,
        format="%(message)s",
    )
    if args.command is None:
        parser.print_help()
        return 0
    try:
        return COMMANDS[args.command](args)
    except ScionError as exc:
        print(f"erreur : {exc}", file=sys.stderr)
        return exc.exit_code


if __name__ == "__main__":
    sys.exit(main())
