import json
import os

from helpers import CWD, CrewCase

import config
import project


def repo(**kw):
    e = {"name": "core", "path": "/w/core", "github": "o/core", "visibility": "private"}
    e.update(kw)
    return e


class Validate(CrewCase):
    def test_a_full_good_file_passes(self):
        data = {"lang": "it", "warn_mb": 400, "tell_user_mb": 800,
                "unattended": {"status_command": ["x", "status"], "active_pattern": "^on",
                               "start_prefixes": ["go"], "ceiling_mb": 1000, "modes": ["auto"]},
                "sessions": [{"name": "boss", "role": "all", "owns": ["a"]}],
                "commit_rules": {"no_coauthor": True, "forbid": [chr(0x2013), chr(0x2014)]},
                "repos": [repo()]}
        self.assertEqual(project.validate(data), ([], []))

    def test_each_wrong_field_is_an_error(self):
        bad = [{"lang": "fr"}, {"warn_mb": 0}, {"warn_mb": True}, {"warn_mb": 900, "tell_user_mb": 800},
               {"unattended": []}, {"unattended": {"status_command": []}},
               {"unattended": {"active_pattern": "("}}, {"unattended": {"modes": ["night"]}},
               {"unattended": {"ceiling_mb": -1}}, {"sessions": [{"role": "x"}]},
               {"sessions": [{"name": "a", "owns": "b"}]}, {"commit_rules": {"extra": 1}},
               {"commit_rules": {"no_coauthor": "yes"}}, {"commit_rules": {"forbid": "ab"}},
               {"repos": [repo(visibility="x")]}, {"repos": "no"}, []]
        for data in bad:
            self.assertTrue(project.validate(data)[0], data)

    def test_an_unknown_field_is_a_warning_not_an_error(self):
        errors, warnings = project.validate({"lang": "en", "extra": 1})
        self.assertEqual(errors, [])
        self.assertIn("extra", warnings[0])


class Diff(CrewCase):
    def test_fields_and_repositories_are_listed_one_by_one(self):
        old = {"lang": "en", "warn_mb": 400, "repos": [repo(), repo(name="web", github="o/web")]}
        new = {"lang": "it", "commit_rules": {"no_coauthor": True},
               "repos": [repo(pushers=["boss"]), repo(name="doc", github="o/doc")]}
        lines = project.diff(old, new)
        self.assertIn('lang: "en" -> "it"', lines)
        self.assertIn("warn_mb: removed", lines)
        self.assertTrue(any(l.startswith("commit_rules: added") for l in lines))
        self.assertIn('repos core: pushers null -> ["boss"]', lines)
        self.assertIn("repos web: removed", lines)
        self.assertTrue(any(l.startswith("repos doc: added") for l in lines))
        self.assertEqual(project.diff(new, new), [])


class Write(CrewCase):
    def test_the_write_keeps_the_previous_file_and_leaves_no_temporary(self):
        self.project(lang="en")
        project.write(CWD, {"lang": "it"})
        path = config.project_file(CWD)
        with open(path) as f:
            self.assertEqual(json.load(f), {"lang": "it"})
        with open(path + ".prev") as f:
            self.assertEqual(json.load(f), {"lang": "en"})
        self.assertFalse(os.path.exists(path + ".tmp"))

    def test_characters_are_written_as_escapes(self):
        project.write(CWD, {"commit_rules": {"forbid": [chr(0x2014)]}})
        with open(config.project_file(CWD)) as f:
            self.assertIn("\\u2014", f.read())

    def test_a_draft_must_live_in_the_drafts_folder(self):
        os.makedirs(project.drafts_dir(CWD))
        good = os.path.join(project.drafts_dir(CWD), "d.json")
        with open(good, "w") as f:
            json.dump({"lang": "en"}, f)
        self.assertEqual(project.read_draft(CWD, "d.json"), {"lang": "en"})
        self.assertEqual(project.read_draft(CWD, good), {"lang": "en"})
        outside = os.path.join(self.tmp, "d.json")
        with open(outside, "w") as f:
            f.write("{}")
        for path in (outside, "../d.json", "missing.json"):
            with self.assertRaises(ValueError):
                project.read_draft(CWD, path)
