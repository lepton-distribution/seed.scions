"""A failed git command is reported by the first line git wrote.

git ends many failures with generic advice ("Please make sure you have the
correct access rights / and the repository exists."): the cause comes first.
The message of a failed command keeps, on a single line, the first line of
git's stderr that states a cause -- ``fatal:`` or ``error:``, in English or in
French --, skipping the warnings and hints git may write before it; without
such a line, the first non-empty line, whatever git's language. ``git clone``
runs with ``--quiet`` so that its progress line does not come first. The whole of git's
stderr is logged at debug level (``-v``).

Every repository is local, reached through ``file://localhost``.
"""

from __future__ import annotations

import subprocess
import unittest
from unittest import mock

from support import run  # noqa: I001 -- puts the repository on sys.path first
from test_clone_checkout import CheckoutCase, git

from scion import gitops
from scion.errors import GitError

ABSENT_CAUSE = "does not appear to be a git repository"
ADVICE = "and the repository exists."


class TestFailureMessages(CheckoutCase):
    def single_error(self, err: str) -> str:
        lines = [line for line in err.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1, err)
        self.assertTrue(lines[0].startswith("erreur : "), err)
        return lines[0]

    def test_clone_of_an_absent_repository_names_the_cause(self):
        self.ordinary("master", self.absent)
        line = self.single_error(self.seed_add(expect=2))
        self.assertIn(ABSENT_CAUSE, line)
        self.assertNotIn(ADVICE, line)

    def test_clone_of_a_directory_outside_git_names_the_cause(self):
        plain_dir = self.base / "repos/nongit"
        (plain_dir / "scion").mkdir(parents=True)
        self.ordinary("master", self.url(plain_dir))
        line = self.single_error(self.seed_add(expect=2))
        self.assertIn(ABSENT_CAUSE, line)

    def test_missing_version_keeps_its_single_line(self):
        self.ordinary("nope", self.plain)
        line = self.single_error(self.seed_add(expect=2))
        self.assertIn("Remote branch nope not found", line)
        self.assertNotIn("Cloning into", line)

    def test_clone_is_quiet(self):
        self.ordinary("nope", self.plain)
        self.assertIn("git clone -b nope --quiet ", self.seed_add(expect=2))

    def test_remote_seed_absent_names_the_cause(self):
        code, _, err = run("seed-add", self.absent, cwd=self.rootstock)
        self.assertEqual(code, 2, err)
        self.assertIn(ABSENT_CAUSE, self.single_error(err))

    def test_fetch_of_a_vanished_origin_names_the_cause(self):
        """The version check of seed-add fetches a branch's upstream."""
        self.ordinary("dev", self.plain)
        self.seed_add()
        git(self.target("dev"), "remote", "set-url", "origin", self.absent)
        line = self.single_error(self.seed_add(expect=2))
        self.assertIn("git fetch --quiet", line)
        self.assertIn(ABSENT_CAUSE, line)
        self.assertNotIn(ADVICE, line)

    def test_ls_remote_of_a_vanished_origin_names_the_cause(self):
        """The version check of seed-add reads a tag in the upstream."""
        self.ordinary("v1", self.plain)
        self.seed_add()
        git(self.target("v1"), "remote", "set-url", "origin", self.absent)
        line = self.single_error(self.seed_add(expect=2))
        self.assertIn("git ls-remote", line)
        self.assertIn(ABSENT_CAUSE, line)


class TestFirstLine(unittest.TestCase):
    """The rule itself, on git output in another language."""

    def failing(self, stderr: str) -> GitError:
        error = subprocess.CalledProcessError(128, ["git"], output="", stderr=stderr)
        with mock.patch.object(gitops.subprocess, "run", side_effect=error):
            with self.assertRaises(GitError) as caught:
                gitops.run(["fetch", "--quiet"])
        return caught.exception

    def test_translated_output_keeps_its_first_line(self):
        nbsp = " "
        exc = self.failing(f"fatal{nbsp}: '/x' does not appear to be a git repository\n"
                           f"fatal{nbsp}: Impossible de lire le dépôt distant.\n\n"
                           "Veuillez vérifier que vous avez les droits d'accès\n"
                           "et que le dépôt existe.\n")
        self.assertEqual(str(exc), "échec de « git fetch --quiet » (code 128) : "
                                   f"fatal{nbsp}: '/x' does not appear to be a git repository")

    def test_warning_before_the_cause_is_skipped(self):
        """git < 2.50 warns first on ``git clone -b <absent> --single-branch``."""
        exc = self.failing("warning: Could not find remote branch nope to clone.\n"
                           "fatal: Remote branch nope not found in upstream origin\n"
                           "fatal: The remote end hung up unexpectedly\n")
        self.assertTrue(str(exc).endswith(
            " : fatal: Remote branch nope not found in upstream origin"), str(exc))

    def test_translated_warning_before_the_cause_is_skipped(self):
        nbsp = " "
        exc = self.failing(f"avertissement{nbsp}: Impossible de trouver la branche distante "
                           "'nope' à cloner.\n"
                           f"fatal{nbsp}: La branche distante nope n'a pas été trouvée dans le "
                           "dépôt amont origin\n")
        self.assertTrue(str(exc).endswith(
            f" : fatal{nbsp}: La branche distante nope n'a pas été trouvée dans le dépôt "
            "amont origin"), str(exc))

    def test_hints_before_the_cause_are_skipped(self):
        """``git merge --ff-only`` on a diverged branch gives its advice first."""
        exc = self.failing("hint: Diverging branches can't be fast-forwarded, you need to "
                           "either:\nhint:\nhint: \tgit merge --no-ff\nhint:\n"
                           "fatal: Not possible to fast-forward, aborting.\n")
        self.assertTrue(str(exc).endswith(" : fatal: Not possible to fast-forward, aborting."),
                        str(exc))

    def test_an_error_line_is_a_cause(self):
        nbsp = " "
        self.assertTrue(str(self.failing("hint: x\nerror: y\nhint: z\n")).endswith(" : error: y"))
        self.assertTrue(str(self.failing(f"astuce{nbsp}: x\nerreur{nbsp}: y\n")).endswith(
            f" : erreur{nbsp}: y"))

    def test_first_cause_wins(self):
        exc = self.failing("error: failed to push some refs\nfatal: later\n")
        self.assertTrue(str(exc).endswith(" : error: failed to push some refs"), str(exc))

    def test_without_a_cause_line_the_first_line_is_kept(self):
        """Another language, or no prefix at all: the rule of 0.6.3.3."""
        exc = self.failing("Warnung: etwas\nSchwerwiegend: Ursache\n")
        self.assertTrue(str(exc).endswith(" : Warnung: etwas"), str(exc))

    def test_cause_is_a_single_line(self):
        exc = self.failing("warning: w\nfatal: cause\nfatal: suite\n")
        self.assertEqual(len(str(exc).splitlines()), 1, str(exc))

    def test_leading_blank_lines_are_skipped(self):
        exc = self.failing("\n  \nfatal: cause\nsuite\n")
        self.assertTrue(str(exc).endswith(" : fatal: cause"), str(exc))

    def test_silent_failure_has_no_detail(self):
        self.assertEqual(str(self.failing("")), "échec de « git fetch --quiet » (code 128)")

    def test_whole_output_travels_and_is_logged(self):
        stderr = "fatal: cause\nfatal: Could not read from remote repository.\n"
        with self.assertLogs("scion.gitops", level="DEBUG") as logs:
            exc = self.failing(stderr)
        self.assertEqual(exc.stderr, stderr)
        self.assertTrue(any("Could not read from remote repository." in line
                            for line in logs.output), logs.output)


if __name__ == "__main__":
    unittest.main()
