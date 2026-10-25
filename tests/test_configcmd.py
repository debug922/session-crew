import contextlib
import io
import json
import os
import subprocess

from helpers import CWD, CrewCase

import config
import configcmd
import project
import repos
from registry import Identity


def sh(cwd, *args):
    subprocess.run(args, cwd=cwd, check=True, capture_output=True)


class Base(CrewCase):
    def setUp(self):
        super().setUp()
        self.real = repos.github_status
        self.addCleanup(setattr, repos, "github_status", self.real)
        self.asked = []

        def status(github):
            self.asked.append(github)
            return {"o/private": 404, "o/public": 200}.get(github, 500)
        repos.github_status = status

    def out(self, fn, *args, **kw):
        buf, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            rc = fn(*args, **kw)
        return rc, buf.getvalue(), err.getvalue()

    def draft(self, data, name="d.json"):
        os.makedirs(project.drafts_dir(CWD), exist_ok=True)
        with open(os.path.join(project.drafts_dir(CWD), name), "w") as f:
            json.dump(data, f)
        return name


class Show(Base):
    def test_no_file_says_so(self):
        rc, out, _ = self.out(configcmd.show, Identity(cwd=CWD))
        self.assertIn("no project file yet", out)

    def test_a_file_is_shown_with_what_it_lacks(self):
        self.project(lang="en")
        _, out, _ = self.out(configcmd.show, Identity(cwd=CWD))
        self.assertIn('"lang": "en"', out)
        for word in ("repos", "commit_rules", "sessions"):
            self.assertIn("lacks " + word, out)

    def test_a_broken_field_is_named(self):
        self.project(warn_mb=-1)
        _, out, _ = self.out(configcmd.show, Identity(cwd=CWD))
        self.assertIn("problem: warn_mb", out)


class Discover(Base):
    def setUp(self):
        super().setUp()
        self.folder = os.path.join(self.tmp, "work")
        for rel, origin in [("a", "git@github.com:o/private.git"), ("b/c", "https://github.com/o/public"),
                            ("d", "git@gitlab.com:o/x.git"), ("e", None), ("n/o/deep", "git@github.com:o/n.git")]:
            path = os.path.join(self.folder, rel)
            os.makedirs(path)
            sh(path, "git", "init", "-q")
            if origin:
                sh(path, "git", "remote", "add", "origin", origin)
        self.elsewhere = os.path.join(self.tmp, "elsewhere")
        os.makedirs(self.elsewhere)
        sh(self.elsewhere, "git", "init", "-q")
        sh(self.elsewhere, "git", "remote", "add", "origin", "git@github.com:o/other.git")

    def found(self):
        _, out, _ = self.out(configcmd.discover, Identity(cwd=self.folder))
        return json.loads(out)

    def test_repositories_two_levels_down_with_origin_and_visibility(self):
        by = {os.path.relpath(r["path"], self.folder): r for r in self.found()["repos_found"]}
        self.assertEqual(sorted(by), ["a", "b/c", "d", "e"])  # n/o/deep is three levels down
        self.assertEqual((by["a"]["github"], by["a"]["visibility"]), ("o/private", "private"))
        self.assertEqual(by["b/c"]["visibility"], "public")
        self.assertEqual((by["d"]["github"], by["d"]["visibility"]), (None, None))
        self.assertIsNone(by["e"]["origin"])
        self.assertNotIn("o/x", self.asked)  # a repository off GitHub is never asked about

    def test_unknown_when_github_cannot_be_asked(self):
        def down(_):
            raise OSError("offline")
        repos.github_status = down
        by = {os.path.relpath(r["path"], self.folder): r for r in self.found()["repos_found"]}
        self.assertEqual(by["a"]["visibility"], "unknown")

    def test_the_table_is_marked_and_its_repositories_elsewhere_are_listed(self):
        project.write(self.folder, {"repos": [
            {"name": "alpha", "path": os.path.join(self.folder, "a"), "github": "o/private", "visibility": "private"},
            {"name": "far", "path": self.elsewhere, "github": "o/other", "visibility": "private"}]})
        out = self.found()
        by = {os.path.relpath(r["path"], self.folder): r for r in out["repos_found"]}
        self.assertEqual(by["a"]["in_table"], "alpha")
        self.assertIsNone(by["b/c"]["in_table"])
        self.assertEqual(by[os.path.relpath(self.elsewhere, self.folder)]["in_table"], "far")
        self.assertEqual(out["current"]["repos"][0]["name"], "alpha")
        self.assertTrue(out["drafts_dir"].endswith("drafts"))

    def test_sessions_are_the_users_names_in_this_folder_live_first(self):
        self.session(os.getpid(), "s1", name="live", cwd=self.folder)
        self.session(2999999, "s2", name="gone", cwd=self.folder)
        self.session(2999998, "s3", name="other", cwd="/elsewhere")
        self.session(2999997, "s4", name="derived", cwd=self.folder)
        path = os.path.join(self.claude, "sessions", "2999997.json")
        with open(path) as f:
            entry = json.load(f)
        entry["nameSource"] = "derived"
        with open(path, "w") as f:
            json.dump(entry, f)
        self.assertEqual(self.found()["sessions"],
                         [{"name": "live", "alive": True}, {"name": "gone", "alive": False}])


class Apply(Base):
    GOOD = {"lang": "en", "commit_rules": {"no_coauthor": True},
            "repos": [{"name": "core", "path": "/w/core", "github": "o/core", "visibility": "private"}]}

    def test_a_draft_is_validated_shown_and_written_with_the_previous_kept(self):
        self.project(lang="it")
        rc, out, _ = self.out(configcmd.apply, Identity(cwd=CWD, session_id="s1"), self.draft(self.GOOD))
        self.assertEqual(rc, 0)
        self.assertIn('lang: "it" -> "en"', out)
        self.assertIn("repos core: added", out)
        self.assertEqual(project.read_current(CWD), self.GOOD)
        with open(config.project_file(CWD) + ".prev") as f:
            self.assertEqual(json.load(f)["lang"], "it")

    def test_an_invalid_draft_writes_nothing(self):
        self.project(lang="it")
        bad = dict(self.GOOD, repos=[{"name": "core"}])
        rc, _, err = self.out(configcmd.apply, Identity(cwd=CWD, session_id="s1"), self.draft(bad))
        self.assertEqual(rc, 1)
        self.assertIn("not a project file", err)
        self.assertEqual(project.read_current(CWD)["lang"], "it")

    def test_a_draft_outside_the_drafts_folder_is_refused(self):
        outside = os.path.join(self.tmp, "x.json")
        with open(outside, "w") as f:
            json.dump(self.GOOD, f)
        rc, _, err = self.out(configcmd.apply, Identity(cwd=CWD, session_id="s1"), outside)
        self.assertEqual(rc, 1)
        self.assertIn("drafts", err)
        self.assertFalse(os.path.exists(config.project_file(CWD)))

    def test_a_draft_equal_to_the_file_changes_nothing(self):
        project.write(CWD, self.GOOD)
        rc, out, _ = self.out(configcmd.apply, Identity(cwd=CWD, session_id="s1"), self.draft(self.GOOD))
        self.assertEqual(rc, 0)
        self.assertIn("nothing changes", out)
        self.assertFalse(os.path.exists(config.project_file(CWD) + ".prev"))

    def test_outside_claude_code_it_writes_only_from_a_terminal_with_a_typed_yes(self):
        ident = Identity(cwd=CWD)
        rc, _, err = self.out(configcmd.apply, ident, self.draft(self.GOOD), ask=lambda _: "yes",
                              tty=lambda: False)
        self.assertEqual(rc, 1)
        self.assertIn("own terminal", err)
        self.assertIn("config apply d.json --cwd", err)
        self.assertFalse(os.path.exists(config.project_file(CWD)))
        rc, out, _ = self.out(configcmd.apply, ident, self.draft(self.GOOD), ask=lambda _: "no",
                              tty=lambda: True)
        self.assertEqual(rc, 1)
        self.assertIn("nothing written", out)
        rc, _, _ = self.out(configcmd.apply, ident, self.draft(self.GOOD), ask=lambda _: " Yes ",
                            tty=lambda: True)
        self.assertEqual(rc, 0)
        self.assertEqual(project.read_current(CWD), self.GOOD)

    def test_the_command_line_wires_the_three_actions(self):
        import crew
        self.project(lang="it")
        self.draft(self.GOOD)
        for argv in (["config", "show"], ["config", "discover"]):
            rc, _, _ = self.out(crew.main, argv + ["--cwd", CWD, "--session-id", "none"])
            self.assertEqual(rc, 0, argv)
        rc, _, err = self.out(crew.main, ["config", "apply", "--cwd", CWD])
        self.assertEqual(rc, 2)
