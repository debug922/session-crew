import http.client
import json
import os

from helpers import CWD, CrewCase

import config
import repos


def entry(name="core", **kw):
    e = {"name": name, "path": "/work/" + name, "github": "o/" + name, "visibility": "private",
         "pushers": ["boss"], "checks": ["unittest"], "tags": None}
    e.update(kw)
    return e


class GithubUrl(CrewCase):
    def test_a_remotes_url_names_its_repository(self):
        for url in ["git@github.com:debug922/x.git", "https://github.com/debug922/x",
                    "https://github.com/Debug922/x.git/", "ssh://git@github.com/debug922/x.git",
                    "https://tok@github.com/debug922/x.git"]:
            self.assertEqual(repos.github_of(url), "debug922/x", url)

    def test_a_url_that_is_not_githubs_names_nothing(self):
        for url in ["/tmp/x.git", "git@gitlab.com:debug922/x.git", "https://github.com.evil/x/y",
                    "https://github.com/debug922", "", None]:
            self.assertIsNone(repos.github_of(url), url)


class Shape(CrewCase):
    def test_a_good_entry_passes_with_every_kind_of_check(self):
        checks = ["go", "frontend", "unittest", {"run": ["make", "test"]},
                  {"run": ["npm", "test"], "in": "web", "when_changed": "web", "in_repo": True}]
        e = entry(checks=checks, tags={"version": "file", "annotated": True}, visibility="public")
        self.assertEqual(repos.problems([e]), [])

    def test_optional_fields_default(self):
        self.assertEqual(repos.problems([{"name": "a", "path": "~/a", "github": "o/a",
                                          "visibility": "private"}]), [])

    def test_each_wrong_shape_is_named(self):
        bad = [entry(name="../x"), entry(path=""), entry(path="rel/x"), entry(github="gitlab"),
               entry(visibility="internal"), entry(pushers="boss"), entry(pushers=["a b"]),
               entry(checks="go"), entry(checks=["make deploy"]), entry(checks=[{"run": []}]),
               entry(checks=[{"run": ["x"], "in": "/abs"}]),
               entry(checks=[{"run": ["x"], "when_changed": "../up"}]),
               entry(checks=[{"run": ["x"], "in_repo": "yes"}]),
               entry(checks=[{"run": ["x"], "shell": True}]),
               entry(tags={"version": "git", "annotated": False}),
               entry(tags={"version": "file"}), "text"]
        for e in bad:
            self.assertEqual(len(repos.problems([e])), 1, e)

    def test_a_twin_name_and_a_non_list_are_named(self):
        self.assertIn("listed twice", repos.problems([entry(), entry()])[0])
        self.assertEqual(repos.problems({}), ["repos is not a list"])


class Reading(CrewCase):
    def test_no_project_file_is_nothing(self):
        t = repos.read(CWD)
        self.assertEqual((t.exists, t.active, t.entries), (False, False, None))

    def test_a_project_without_repos_exists_but_the_flow_is_idle(self):
        self.project()
        t = repos.read(CWD)
        self.assertEqual((t.exists, t.active), (True, False))
        with self.assertRaisesRegex(ValueError, "no list"):
            repos.load(CWD)

    def test_an_empty_table_is_idle_and_a_filled_one_active(self):
        self.project(repos=[])
        self.assertEqual((repos.read(CWD).active, repos.read(CWD).entries), (False, {}))
        self.project(repos=[entry(path="~/x")])
        t = repos.read(CWD)
        self.assertTrue(t.active)
        self.assertEqual(t.entries["core"]["path"], os.path.expanduser("~/x"))

    def test_a_file_that_cannot_be_read_or_has_a_bad_entry_is_active_and_refuses(self):
        folder = os.path.join(self.crew_home, "-work-proj")
        os.makedirs(folder)
        with open(os.path.join(folder, "project.json"), "w") as f:
            f.write("{")
        t = repos.read(CWD)
        self.assertEqual((t.exists, t.active, t.entries), (True, True, None))
        self.assertIn("cannot be read", t.error)
        self.project(repos=[entry(checks=["make deploy"])])
        self.assertTrue(repos.read(CWD).active)
        with self.assertRaisesRegex(ValueError, "not a preset"):
            repos.load(CWD)

    def test_locate_finds_the_nearest_folder_with_a_project(self):
        self.project()
        self.assertEqual(config.locate(CWD + "/sub/deeper"), CWD)
        self.assertEqual(config.locate(CWD), CWD)
        self.assertIsNone(config.locate("/elsewhere/x"))


class Presets(CrewCase):
    def test_go_runs_in_three_steps_with_the_limit_of_the_mode(self):
        day = repos.expand_checks(["go"], night=False)
        night = repos.expand_checks(["go"], night=True)
        self.assertEqual([c["run"][:2] for c in day], [["go", "vet"], ["go", "test"], ["govulncheck", "./..."]])
        self.assertIn("2", day[1]["run"])
        self.assertIn("8", night[1]["run"])
        self.assertTrue(all(c["env"] == {"GOWORK": "off"} for c in day))

    def test_unittest_and_frontend_and_own_objects(self):
        self.assertEqual(repos.expand_checks(["unittest"], False)[0]["run"][:3], ["python3", "-I", "-m"])
        front = repos.expand_checks(["frontend"], False)
        self.assertEqual([c["run"] for c in front], [["npm", "run", "typecheck"], ["npm", "test"]])
        self.assertTrue(all(c["in_repo"] and c["when_changed"] == "frontend" and c["env"] == {"CI": "true"}
                            for c in front))
        own = {"run": ["make"], "in": "x"}
        self.assertEqual(repos.expand_checks([own], False), [own])


class Visibility(CrewCase):
    def test_visibility_is_read_from_the_status_and_unknown_when_not_asked(self):
        real = repos.github_status
        self.addCleanup(setattr, repos, "github_status", real)
        for status, want in [(404, "private"), (200, "public"), (403, "unknown")]:
            repos.github_status = lambda g, s=status: s
            self.assertEqual(repos.visibility_of("o/x"), want)

        for exc in (OSError("offline"), http.client.RemoteDisconnected("closed"),
                    http.client.IncompleteRead(b"x"), ValueError("odd")):
            def down(_, exc=exc):
                raise exc
            repos.github_status = down
            self.assertEqual(repos.visibility_of("o/x"), "unknown", exc)
