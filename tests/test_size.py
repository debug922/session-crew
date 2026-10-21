import json
import os
import sys

from helpers import CWD, CrewCase, ROOT

import size


def hook(case, mb, prompt="hello", sid="s1"):
    path = case.transcript(sid, mb)
    event = {"session_id": sid, "cwd": CWD, "transcript_path": path, "prompt": prompt}
    rc, out, _ = case.call(size.hook, event)
    out = out or {}
    ctx = out.get("hookSpecificOutput", {}).get("additionalContext")
    return rc, ctx, out.get("systemMessage")


class AttendedTable(CrewCase):
    def setUp(self):
        super().setUp()
        self.project()  # Italian, as the messages below
        self.session(100, "s1", "alpha")

    def test_below_warn_nothing(self):
        self.assertEqual(hook(self, 399), (0, None, None))

    def test_below_warn_with_pending_tells_maintainer(self):
        self.pending("alpha")
        rc, ctx, msg = hook(self, 10)
        self.assertIsNone(ctx)
        self.assertEqual(msg, "Passaggio pronto: scrivi /clear e poi /migrate.")

    def test_warn_tells_session_only(self):
        rc, ctx, msg = hook(self, 450)
        self.assertIn("/handoff", ctx)
        self.assertIn("no new item", ctx)
        self.assertIsNone(msg)

    def test_warn_with_pending_gives_the_pending_line(self):
        self.pending("alpha")
        rc, ctx, msg = hook(self, 450)
        self.assertNotIn("/handoff", ctx)
        self.assertIn("already written", ctx)
        self.assertIn("Passaggio pronto", msg)

    def test_tell_user(self):
        rc, ctx, msg = hook(self, 850)
        self.assertIn("/handoff", ctx)
        self.assertEqual(msg, "Questa sessione pesa 850 MB: /handoff, /clear, /migrate.")

    def test_english(self):
        self.project(lang="en")
        _, _, msg = hook(self, 850)
        self.assertEqual(msg, "This session weighs 850 MB: /handoff, /clear, /migrate.")

    def test_default_language_is_english(self):
        os.remove(os.path.join(self.crew_home, "-work-proj", "project.json"))
        self.assertEqual(hook(self, 850)[2], "This session weighs 850 MB: /handoff, /clear, /migrate.")

    def test_missing_transcript_is_zero(self):
        rc, out, _ = self.call(size.hook, {"session_id": "s1", "cwd": CWD,
                                           "transcript_path": "/nope", "prompt": "x"})
        self.assertEqual((rc, out), (0, None))


class Night(CrewCase):
    def setUp(self):
        super().setUp()
        self.session(100, "s1", "alpha")

    def config(self, mode_line):
        self.project(unattended={
            "status_command": ["sh", "-c", "echo '%s'" % mode_line],
            "active_pattern": "^mode: full", "start_prefixes": ["vai in modalità full"],
            "ceiling_mb": 1000})

    def test_start_prefix_over_warn(self):
        self.config("mode: off")
        rc, ctx, msg = hook(self, 450, prompt="  Vai in modalità full stasera")
        self.assertIn("Do not start the unattended run", ctx)
        self.assertEqual(msg, "Questa sessione pesa 450 MB: prima della notte /handoff, /clear, "
                              "/migrate, poi ripeti il comando.")

    def test_start_prefix_under_warn(self):
        self.config("mode: off")
        self.assertEqual(hook(self, 100, prompt="vai in modalità full"), (0, None, None))

    def test_unattended_below_ceiling_is_silent_even_over_warn(self):
        self.config("mode: full")
        self.assertEqual(hook(self, 900), (0, None, None))

    def test_unattended_over_ceiling_parks_without_telling_him(self):
        self.config("mode: full")
        self.pending("alpha")
        rc, ctx, msg = hook(self, 1100)
        self.assertIn("Park the queue", ctx)
        self.assertIsNone(msg)

    def test_failing_status_command_counts_as_attended(self):
        self.project(unattended={"status_command": ["/nonexistent/cmd"],
                                 "active_pattern": "^mode: full", "ceiling_mb": 1000})
        rc, ctx, msg = hook(self, 450)
        self.assertIn("/handoff", ctx)


class Entry(CrewCase):
    def test_hook_error_exits_one_and_prints_to_stderr(self):
        import subprocess
        r = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "scripts", "crew.py"),
                            "hook", "size"], input="not json", capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("session-crew hook size", r.stderr)

    def test_size_command_by_hand(self):
        import subprocess
        path = self.transcript("zz", 450)
        r = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "scripts", "crew.py"),
                            "size", path, "--cwd", CWD], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("450.0 MB", r.stdout)
        self.assertIn("/handoff", r.stdout)
