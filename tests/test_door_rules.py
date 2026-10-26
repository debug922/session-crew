"""The door's pure rules: which version may follow, GitHub's answers, origin."""
import os
import subprocess

from helpers import CrewCase

import door
import repos


def sh(cwd, *args):
    out = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if out.returncode != 0:
        raise AssertionError("%s: %s" % (args, out.stderr))
    return out.stdout.strip()


class Next(CrewCase):
    def test_the_next_patch_or_minor_follows(self):
        for last, new in [("v0.41.1", "v0.41.2"), ("v0.41.1", "v0.42.0"), (None, "v0.1.0")]:
            self.assertIsNone(door.why_not_next(last, new), (last, new))

    def test_a_new_x_a_skip_a_step_back_or_a_bad_form_do_not(self):
        for last, new in [("v0.41.1", "v1.0.0"), (None, "v1.0.0"), ("v0.41.1", "v0.43.0"),
                          ("v0.41.1", "v0.41.3"), ("v0.41.1", "v0.41.1"), ("v0.41.1", "v0.40.9"),
                          ("v0.41.1", "v0.42.1"), ("v0.41.1", "0.42.0"), ("v0.41.1", "v0.42")]:
            self.assertIsNotNone(door.why_not_next(last, new), (last, new))


class GitHub(CrewCase):
    def test_only_a_404_lets_a_private_repository_go(self):
        self.assertIsNone(door.why_not_private("o/x", 404))
        self.assertIn("public on GitHub now", door.why_not_private("o/x", 200))
        for status in (403, 500, 301):
            self.assertIn("unknown", door.why_not_private("o/x", status))

    def test_origin_must_be_the_tables_repository_for_fetch_and_push(self):
        repo = os.path.join(self.tmp, "r")
        os.makedirs(repo)
        sh(repo, "git", "init", "-q")
        sh(repo, "git", "remote", "add", "origin", "git@github.com:o/x.git")
        self.assertIsNone(door.origin_faults(repo, {"github": "o/x"}))
        self.assertIsNone(door.origin_faults(repo, {"github": "O/X"}))
        self.assertIn("not github.com:o/y", door.origin_faults(repo, {"github": "o/y"}))
        sh(repo, "git", "remote", "set-url", "--push", "origin", "git@github.com:someone/else.git")
        self.assertIn("--push", door.origin_faults(repo, {"github": "o/x"}))

    def test_a_failure_to_ask_github_refuses_a_private_repository(self):
        def down(_):
            raise OSError("offline")
        saved = repos.github_status
        self.addCleanup(setattr, repos, "github_status", saved)
        repos.github_status = down
        self.assertIn("nothing is pushed unchecked", door.private_fault("o/x"))
