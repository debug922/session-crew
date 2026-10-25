"""The door's line in the Bash guard: who may run it, in which shape, for which repository."""
import json
import os

from guardhelp import GuardCase

import config
import guard


class DoorLine(GuardCase):
    def line(self, repo="lib", action="push"):
        return "python3 -I \"%s\" %s %s" % (guard.CREW, action, repo)

    def test_the_session_the_table_names_passes_in_every_quoting_of_the_path(self):
        for cmd in [self.line(), self.line("core", "tag") + " v0.2.0",
                    "python3 -I '%s' push lib" % guard.CREW, "python3 -I %s push lib" % guard.CREW,
                    "  " + self.line() + "\n"]:
            self.assertIsNone(self.bash(cmd), cmd)

    def test_one_of_its_agents_does_not(self):
        self.assertEqual(self.bash(self.line(), agent_id="a1b2", agent_type="runner"), "deny")

    def test_another_session_or_a_name_that_is_not_the_users_does_not(self):
        self.session(200, "s-other", "helper-x", cwd=self.work)
        self.session(300, "s-derived", "boss", cwd=self.work)
        path = os.path.join(self.claude, "sessions", "300.json")
        with open(path) as f:
            entry = json.load(f)
        entry["nameSource"] = "derived"
        with open(path, "w") as f:
            json.dump(entry, f)
        for sid in ["s-other", "s-derived", "s-unknown", ""]:
            self.assertEqual(self.bash(self.line(), sid=sid), "deny", sid)

    def test_a_second_pusher_of_a_repository_passes_and_the_others_do_not(self):
        self.session(200, "s-helper", "helper", cwd=self.work)
        self.assertIsNone(self.bash(self.line("lib"), sid="s-helper"))
        self.assertEqual(self.bash(self.line("core"), sid="s-helper"), "deny")

    def test_the_latest_entry_of_a_session_decides(self):
        self.session(400, "s-4", "boss", cwd=self.work)
        self.session(401, "s-4", "renamed", cwd=self.work)
        with open(os.path.join(self.claude, "sessions", "401.json")) as f:
            newer = json.load(f)
        newer["updatedAt"] = 5
        with open(os.path.join(self.claude, "sessions", "401.json"), "w") as f:
            json.dump(newer, f)
        self.assertEqual(self.bash(self.line(), sid="s-4"), "deny")

    def test_any_other_shape_of_the_line_is_denied(self):
        for cmd in [self.line() + " && rm -rf x", self.line() + " | tee log", self.line() + " 2>&1",
                    "python3 \"%s\" push lib" % guard.CREW,
                    self.line("../lib"), self.line("lib", "tag") , self.line("lib", "tag") + " 0.2.0",
                    self.line("lib", "tag") + " v1",
                    "python3 -I /tmp/copy/scripts/crew.py push lib",
                    "cd scripts && python3 -I crew.py push lib",
                    "bash -c '%s'" % self.line(), "cd /tmp && " + self.line()]:
            self.assertEqual(self.bash(cmd), "deny", cmd)

    def test_a_repository_outside_the_table_or_without_tags_is_denied(self):
        self.assertEqual(self.bash(self.line("other")), "deny")
        self.assertEqual(self.bash(self.line("lib", "tag") + " v0.2.0"), "deny")  # lib has no tags
        self.assertIsNone(self.bash(self.line("core", "tag") + " v0.2.0"))

    def test_a_public_repository_asks_by_day_and_is_refused_at_night(self):
        self.night(False)
        self.assertEqual(self.bash(self.line("site")), "ask")
        self.night(True)
        self.assertEqual(self.bash(self.line("site")), "deny")
        self.assertIsNone(self.bash(self.line("lib")))  # the night does not close a private door

    def test_a_table_missing_broken_or_of_another_shape_denies_the_door(self):
        good = self.entries[0]
        for entries in [[dict(good, pushers="boss")], [good, good], [dict(good, visibility="x")],
                        [dict(good, checks=["make deploy"])], [dict(good, tags={"version": "git"})],
                        "text"]:
            self.table(entries)
            self.assertEqual(self.bash(self.line("core")), "deny", entries)
        with open(config.project_file(self.work), "w") as f:
            f.write("{")
        self.assertEqual(self.bash(self.line("core")), "deny")
        self.table({})  # repos that is not a list
        os.remove(config.project_file(self.work))
        self.assertIsNone(self.bash(self.line("core")))  # no project file: nothing is said

    def test_a_registry_that_cannot_be_read_denies(self):
        os.rename(os.path.join(self.claude, "sessions"), os.path.join(self.claude, "gone"))
        self.assertEqual(self.bash(self.line()), "deny")

    def test_a_door_named_in_a_message_is_no_door(self):
        for cmd in ['git commit -q -m "Say crew.py push lib is the door"',
                    "git commit -F - <<'EOF'\nPush through crew.py push lib\nEOF"]:
            self.assertIsNone(self.bash(cmd, sid="s-other"), cmd)
        self.assertEqual(self.bash('git commit -m "x" && ' + self.line(), sid="s-other"), "deny")

    def test_a_crash_on_a_door_denies_and_any_other_crash_lets_the_command_through(self):
        rc, out, _ = self.call(guard.run_bash, "not json, crew.py push lib")
        self.assertEqual((rc, out["hookSpecificOutput"]["permissionDecision"]), (0, "deny"))
        import contextlib
        import io
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc, out, _ = self.call(guard.run_bash, "not json")
        self.assertEqual((rc, out), (1, None))
        self.assertIn("failed open", err.getvalue())
