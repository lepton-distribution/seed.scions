"""A failed git command is reported by the first line git wrote.

git ends many failures with generic advice ("Please make sure you have the
correct access rights / and the repository exists."): the cause comes first.
The message of a failed command keeps the first non-empty line of git's
stderr, whatever git's language, on a single line; ``git clone`` runs with
``--quiet`` so that its progress line does not come first. The whole of git's
stderr is logged at debug level (``-v``).

Every repository is local, reached through ``file://localhost``.
"""

from __future__ import annotations

import subprocess
import unittest
from unittest import mock

from scion import gitops
from scion.errors import GitError
from support import run
from test_clone_checkout import CheckoutCase, git

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
