"""The door (door.py), ported from the first project that used it: throwaway repositories with a
bare repository beside each as origin, GitHub's answer and origin's check stubbed, checks stubbed."""
import contextlib
import io
import json
import os
import subprocess
import sys
import unittest.mock

from helpers import CWD, CrewCase

import config
import door
import project
import repos
from gitrun import Refused
from registry import Identity

LONG = chr(0x2014)
MEDIUM = chr(0x2013)


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


class Repo(CrewCase):
    """core (changelog tags), lib (VERSION, annotated tags), app (no tags), site (public)."""

    def setUp(self):
        super().setUp()
        self.root = os.path.join(self.tmp, "repos")
        os.makedirs(self.root)
        self.status = 404
        saved = repos.github_status, door.origin_faults
        self.addCleanup(lambda: (setattr(repos, "github_status", saved[0]),
                                 setattr(door, "origin_faults", saved[1])))
        repos.github_status = lambda github: self.status
        door.origin_faults = lambda repo_dir, entry: None
        self.built = []
        entries = []
        for name, file, text, tags, visibility in [
                ("core", "CHANGELOG.md", "# Changelog\n\n## v0.41.1 (2026-10-20)\n",
                 {"version": "changelog", "annotated": False}, "private"),
                ("lib", "VERSION", "0.2.0\n", {"version": "file", "annotated": True}, "private"),
                ("app", "README.md", "app\n", None, "private"),
                ("site", "README.md", "site\n", None, "public")]:
            bare = os.path.join(self.root, name + ".git")
            sh(self.root, "git", "init", "-q", "--bare", "-b", "main", bare)
            sh(self.root, "git", "clone", "-q", bare, name)
            self.commit(name, file, text, "Start")
            self.git(name, "push", "-q", "origin", "main")
            if name == "core":
                self.git(name, "tag", "v0.41.1")
            elif name == "lib":
                self.git(name, "tag", "-a", "v0.2.0", "-m", "v0.2.0")
            self.git(name, "push", "-q", "origin", "--tags")
            entries.append({"name": name, "path": os.path.join(self.root, name), "github": "t/" + name,
                            "visibility": visibility, "pushers": ["boss"], "checks": ["unittest"],
                            "tags": tags})
        self.entries = entries
        self.project(repos=entries, commit_rules={"no_coauthor": True, "forbid": [MEDIUM, LONG]})

    def git(self, name, *args):
        return sh(os.path.join(self.root, name), "git", "-c", "user.name=t", "-c", "user.email=t@t", *args)

    def commit(self, name, file, text, message):
        with open(os.path.join(self.root, name, file), "w", encoding="utf-8") as fh:
            fh.write(text)
        self.git(name, "add", file)
        self.git(name, "commit", "-q", "-m", message)

    def release(self, name, version=None, caller="boss"):
        return door.release(CWD, name, version, caller, build=lambda *a: self.built.append(a))

    def remote(self, name, *args):
        return sh(os.path.join(self.root, name + ".git"), "git", *args)

    def test_a_tag_pushes_main_then_the_tag_in_the_repositorys_own_style(self):
        self.commit("core", "CHANGELOG.md", "# Changelog\n\n## v0.42.0 (2026-10-21)\n\n## v0.41.1 (2026-10-20)\n", "Name v0.42.0")
        self.assertIn("tagged v0.42.0", self.release("core", "v0.42.0"))
        self.assertEqual([b[0] for b in self.built], ["core"])
        self.assertEqual(self.built[0][3], "v0.41.1")  # the tag checks compare against the last tag
        self.assertEqual(self.remote("core", "rev-parse", "main"), self.git("core", "rev-parse", "HEAD"))
        self.assertEqual(self.remote("core", "cat-file", "-t", "v0.42.0"), "commit")
        self.commit("lib", "VERSION", "0.3.0\n", "Name 0.3.0")
        self.release("lib", "v0.3.0")
        self.assertEqual(self.remote("lib", "cat-file", "-t", "v0.3.0"), "tag")

    def test_a_push_alone_runs_the_checks_and_a_push_with_nothing_new_does_not(self):
        self.assertIn("nothing to push", self.release("lib"))
        self.assertEqual(self.built, [])
        self.commit("lib", "a.txt", "a\n", "Add a")
        self.assertIn("pushed 1 commit(s)", self.release("lib"))
        self.assertEqual(self.built[0][3], "origin/main")

    def test_the_checks_are_told_whether_a_night_is_on(self):
        self.commit("lib", "a.txt", "a\n", "Add a")
        self.release("lib")
        self.assertIs(self.built[-1][4], False)
        self.project(repos=self.entries,
                     unattended={"status_command": [sys.executable, "-c", "print('mode: night')"],
                                 "active_pattern": "^mode: night"})
        self.commit("lib", "b.txt", "b\n", "Add b")
        self.release("lib")
        self.assertIs(self.built[-1][4], True)

    def test_a_repository_without_tags_pushes_and_never_tags(self):
        self.commit("app", "a.txt", "a\n", "Add a")
        with self.assertRaisesRegex(Refused, "tags are the user's"):
            self.release("app", "v0.1.0")
        self.assertEqual(self.built, [])
        self.assertIn("pushed 1 commit(s)", self.release("app"))
        self.assertEqual(self.remote("app", "tag", "-l"), "")

    def test_a_private_repository_found_public_or_unknown_is_refused_before_any_build(self):
        self.commit("lib", "a.txt", "a\n", "Add a")
        self.status = 200
        with self.assertRaisesRegex(Refused, "public on GitHub now"):
            self.release("lib")
        self.status = 403
        with self.assertRaisesRegex(Refused, "unknown"):
            self.release("lib")
        self.assertEqual(self.built, [])
        self.assertEqual(self.remote("lib", "rev-list", "--count", "main"), "1")

    def test_a_public_repository_is_not_asked_of_github(self):
        def asked(github):
            raise AssertionError("GitHub asked about %s" % github)
        repos.github_status = asked
        self.commit("site", "a.txt", "a\n", "Add a")
        self.assertIn("pushed 1 commit(s)", self.release("site"))

    def test_origin_not_the_tables_repository_is_refused(self):
        door.origin_faults = lambda repo_dir, entry: "origin is elsewhere"
        self.commit("lib", "a.txt", "a\n", "Add a")
        with self.assertRaisesRegex(Refused, "origin is elsewhere"):
            self.release("lib")
        self.assertEqual(self.built, [])

    def test_the_version_must_be_written_in_the_commit(self):
        self.commit("core", "CHANGELOG.md", "# Changelog\n\n## Unreleased (v0.42.0)\n", "Note")
        with self.assertRaisesRegex(Refused, "no '## v0.42.0 \\(date\\)'"):
            self.release("core", "v0.42.0")
        with self.assertRaisesRegex(Refused, "VERSION at HEAD says 0.2.0"):
            self.release("lib", "v0.3.0")
        self.assertEqual(self.built, [])

    def test_a_new_x_is_refused_before_any_build(self):
        self.commit("lib", "VERSION", "1.0.0\n", "Name 1.0.0")
        with self.assertRaisesRegex(Refused, "user's"):
            self.release("lib", "v1.0.0")
        self.assertEqual(self.built, [])
        self.assertEqual(self.remote("lib", "tag", "-l", "v1.0.0"), "")

    def test_a_message_breaking_the_rules_is_refused(self):
        self.commit("lib", "a.txt", "a\n", "Add a\n\nCo-Authored-By: x <x@y>")
        with self.assertRaisesRegex(Refused, "co-author"):
            self.release("lib")
        self.git("lib", "reset", "-q", "--hard", "origin/main")
        for dash in (LONG, MEDIUM):
            self.commit("lib", "a.txt", "a\n", "Add a %s quickly" % dash)
            with self.assertRaisesRegex(Refused, "forbids"):
                self.release("lib")
            self.git("lib", "reset", "-q", "--hard", "origin/main")

    def test_without_commit_rules_the_messages_are_not_judged(self):
        self.project(repos=self.entries)
        self.commit("lib", "a.txt", "a\n", "Add a %s quickly\n\nCo-Authored-By: x <x@y>" % LONG)
        self.assertIn("pushed 1 commit(s)", self.release("lib"))

    def test_origin_ahead_is_refused_and_nothing_is_forced(self):
        other = os.path.join(self.root, "other")
        sh(self.root, "git", "clone", "-q", os.path.join(self.root, "lib.git"), other)
        sh(other, "git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "Elsewhere")
        sh(other, "git", "push", "-q", "origin", "main")
        self.commit("lib", "a.txt", "a\n", "Add a")
        with self.assertRaisesRegex(Refused, "origin moved"):
            self.release("lib")
        self.assertEqual(self.built, [], "the checks ran for a push that could not go")
        self.assertEqual(self.remote("lib", "log", "-1", "--format=%s", "main"), "Elsewhere")

    def test_a_taken_tag_another_branch_or_a_repository_outside_the_table_are_refused(self):
        self.commit("lib", "VERSION", "0.3.0\n", "Name 0.3.0")
        self.remote("lib", "tag", "v0.3.0", "main")
        with self.assertRaisesRegex(Refused, "taken"):
            self.release("lib", "v0.3.0")
        self.git("lib", "checkout", "-q", "-b", "side")
        with self.assertRaisesRegex(Refused, "not on main"):
            self.release("lib")
        with self.assertRaisesRegex(Refused, "not in the project's table"):
            self.release("elsewhere")

    def test_a_table_that_cannot_be_read_refuses(self):
        self.project(repos=[{"name": "lib"}])
        with self.assertRaisesRegex(Refused, "path missing"):
            self.release("lib")
        os.remove(os.path.join(self.crew_home, "-work-proj", "project.json"))
        with self.assertRaisesRegex(Refused, "no project file"):
            self.release("lib")

    def test_a_failed_build_publishes_nothing(self):
        self.commit("lib", "a.txt", "a\n", "Add a")

        def broken(*_):
            raise Refused("tests failed")
        with self.assertRaisesRegex(Refused, "tests failed"):
            door.release(CWD, "lib", None, "boss", build=broken)
        self.assertEqual(self.remote("lib", "rev-list", "--count", "main"), "1")

    def test_the_door_checks_the_caller_itself(self):
        self.commit("lib", "a.txt", "a\n", "Add a")
        for caller in ("helper", None, ""):
            with self.assertRaisesRegex(Refused, "pushed by boss"):
                self.release("lib", caller=caller)
        self.assertEqual(self.built, [])

    def test_a_public_repository_is_refused_while_a_night_is_on(self):
        self.commit("site", "a.txt", "a\n", "Add a")
        night = {"status_command": [sys.executable, "-c", "print('mode: night')"],
                 "active_pattern": "^mode: night"}
        self.project(repos=self.entries, unattended=night)
        with self.assertRaisesRegex(Refused, "nobody is here"):
            self.release("site")
        self.project(repos=self.entries)  # by day the guard asks and the door goes on
        self.assertIn("pushed 1 commit(s)", self.release("site"))

    def run_cli(self, action, *args, cwd=CWD, session="boss"):
        """The command's own path: caller from the ancestry (stubbed), project from the folder."""
        entry = None if session is None else {"pid": 1, "name": session, "nameSource": "user",
                                              "cwd": "/registry/says/another/folder"}
        stderr = io.StringIO()
        with unittest.mock.patch("registry.find_by_ancestry", return_value=entry), \
                unittest.mock.patch("door.release", side_effect=lambda *a, **k: "done:%s" % (a[3],)), \
                contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(stderr):
            rc = door.run_command(action, *args, cwd=cwd)
        return rc, out.getvalue(), stderr.getvalue()

    def test_no_claude_code_session_above_the_process_is_no_door(self):
        rc, _, err = self.run_cli("push", "lib", session=None)
        self.assertEqual(rc, 1)
        self.assertIn("Claude Code session only", err)

    def test_the_session_that_calls_is_the_one_found_by_ancestry(self):
        rc, out, _ = self.run_cli("push", "lib")
        self.assertEqual((rc, out.strip()), (0, "done:boss"))
        entry = {"pid": 1, "name": "boss", "nameSource": "derived"}
        with unittest.mock.patch("registry.find_by_ancestry", return_value=entry), \
                unittest.mock.patch("door.release", side_effect=lambda *a, **k: "done:%s" % (a[3],)), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            door.run_command("push", "lib", cwd=CWD)
        self.assertEqual(out.getvalue().strip(), "done:None")  # a name that is not his is no name

    def test_the_project_is_the_processs_folder_not_the_registrys(self):
        other = os.path.join(self.tmp, "project-a")
        os.makedirs(other)
        project.write(other, {"repos": []})
        mark = []
        entry = {"pid": 1, "name": "boss", "nameSource": "user", "cwd": other}  # the registry says A
        with unittest.mock.patch("registry.find_by_ancestry", return_value=entry), \
                unittest.mock.patch("door.release", side_effect=lambda cwd, *a, **k: mark.append(cwd) or "ok"), \
                contextlib.redirect_stdout(io.StringIO()):
            door.run_command("push", "lib", cwd=CWD)  # the process is in B (CWD)
        self.assertEqual(mark, [CWD])
        self.assertTrue(os.path.exists(os.path.join(self.crew_home, "-work-proj", "releases.log")))
        self.assertFalse(os.path.exists(os.path.join(config.project_dir(other), "releases.log")))

    def test_every_run_is_logged_beside_the_project_file(self):
        self.commit("lib", "a.txt", "a\n", "Add a")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(self.run_cli("tag", "lib", "v9.0.0", session="helper")[0], 0)  # stub release
            self.assertEqual(door.run_command("push", "lib", cwd="/elsewhere/x"), 1)
        with open(os.path.join(self.crew_home, "-work-proj", "releases.log"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("lib tag v9.0.0: done:helper", text)
        self.assertEqual(text.count("\n"), 1)  # the folder with no project file logged nothing
