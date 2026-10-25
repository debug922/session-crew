"""The checks (checks.py) run for real in a throwaway repository: a failing one refuses, a clean
worktree is used and removed, a folder watched by `when_changed` decides whether a check runs."""
import os
import subprocess

from helpers import CrewCase

import checks
from gitrun import Refused


def sh(cwd, *args):
    subprocess.run(args, cwd=cwd, check=True, capture_output=True)


class Checks(CrewCase):
    def setUp(self):
        super().setUp()
        self.repo = os.path.join(self.tmp, "r")
        os.makedirs(os.path.join(self.repo, "tests"))
        sh(self.repo, "git", "init", "-q", "-b", "main")
        self.write("tests/test_a.py", "import unittest\nclass T(unittest.TestCase):\n"
                                      "    def test_a(self):\n        self.assertTrue(True)\n")
        self.write("web/x.txt", "x\n")
        self.commit("Start")
        sh(self.repo, "git", "tag", "base")

    def write(self, rel, text):
        path = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)

    def commit(self, message):
        sh(self.repo, "git", "add", "-A")
        sh(self.repo, "git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", message)

    def go(self, items, night=False, since="base"):
        checks.run_checks("r", self.repo, {"checks": items}, since, night)

    def worktrees(self):
        out = subprocess.run(["git", "-C", self.repo, "worktree", "list"], capture_output=True, text=True)
        return out.stdout.count("\n")

    def test_no_checks_build_nothing(self):
        self.go([])
        self.assertEqual(self.worktrees(), 1)

    def test_the_unittest_preset_passes_and_the_worktree_is_gone(self):
        self.go(["unittest"])
        self.assertEqual(self.worktrees(), 1)

    def test_a_failing_check_refuses_with_its_output_and_still_cleans_up(self):
        self.write("tests/test_b.py", "import unittest\nclass T(unittest.TestCase):\n"
                                      "    def test_b(self):\n        self.fail('boom')\n")
        self.commit("Break")
        with self.assertRaisesRegex(Refused, "boom"):
            self.go(["unittest"])
        self.assertEqual(self.worktrees(), 1)

    def test_the_checks_test_the_commit_not_the_working_copy(self):
        self.write("tests/test_b.py", "import unittest\nclass T(unittest.TestCase):\n"
                                      "    def test_b(self):\n        self.fail('boom')\n")  # not committed
        self.go(["unittest"])

    def test_an_object_runs_in_its_folder_with_its_argv(self):
        self.go([{"run": ["sh", "-c", "test -f x.txt"], "in": "web"}])
        with self.assertRaises(Refused):
            self.go([{"run": ["sh", "-c", "test -f nothing"], "in": "web"}])

    def test_a_watched_folder_decides_whether_a_check_runs(self):
        fail = {"run": ["sh", "-c", "exit 1"], "when_changed": "web"}
        self.go([fail])  # web unchanged since base: skipped
        self.write("web/x.txt", "y\n")
        self.commit("Change web")
        with self.assertRaises(Refused):
            self.go([fail])

    def test_a_check_in_the_repository_refuses_uncommitted_changes_in_its_folder(self):
        item = {"run": ["sh", "-c", "exit 0"], "in": "web", "when_changed": "web", "in_repo": True}
        self.write("web/x.txt", "y\n")
        self.commit("Change web")
        self.go([item])
        self.write("web/x.txt", "z\n")
        with self.assertRaisesRegex(Refused, "uncommitted"):
            self.go([item])

    def test_the_preset_environment_reaches_the_command(self):
        self.write("web/x.txt", "y\n")
        self.commit("Change web")
        probe = {"run": ["sh", "-c", 'test "$CI" = true'], "in": "web", "in_repo": True,
                 "when_changed": "web"}
        # A user object has no env field; the frontend preset sets CI=true for its npm commands.
        env = {k: v for k, v in os.environ.items() if k != "CI"}  # CI itself is set on GitHub
        with self.assertRaises(Refused):
            checks.run_item(probe, self.repo, self.repo, [], env)
        checks.run_item(dict(probe, env={"CI": "true"}), self.repo, self.repo, [], env)
