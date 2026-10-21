import os
import signal
import subprocess
import time
import unittest.mock

from helpers import CWD, CrewCase

import registry
import rename


def spawn(script):
    """A real child in its own process group, killed at cleanup."""
    return subprocess.Popen(script, shell=isinstance(script, str), start_new_session=True,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class RenameHook(CrewCase):
    def setUp(self):
        super().setUp()
        self.session(100, "me", "newtab")
        self.pending("kcalloc")

    def run_hook(self, prompt, sid="me"):
        event = {"session_id": sid, "cwd": CWD, "prompt": prompt}
        rc, out, _ = self.call(rename.hook, event)
        self.assertEqual(rc, 0)
        return (out or {}).get("hookSpecificOutput")

    @staticmethod
    def reap(proc):
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()

    def child(self, script, name="kcalloc", status="idle"):
        proc = spawn(script)
        self.addCleanup(self.reap, proc)
        self.session(proc.pid, "old", name, status)
        return proc

    def test_other_prompts_do_nothing(self):
        for prompt in ["hello", "/migrate", "/migrate a b", "please /migrate kcalloc",
                       "ok then\n/migrate kcalloc", "/migrate ../x", "/migrate kcalloc now",
                       "/other-plugin:migrate kcalloc", "/session-crew:migrate",
                       "/session-crew: migrate kcalloc"]:
            self.assertIsNone(self.run_hook(prompt), prompt)

    def test_no_pending_handoff_does_nothing(self):
        self.assertIsNone(self.run_hook("/migrate other"))

    def test_pending_of_another_folder_does_nothing(self):
        self.pending("elsewhere", cwd="/other/dir")
        self.assertIsNone(self.run_hook("/migrate elsewhere"))

    def test_already_called_that_does_nothing(self):
        self.session(100, "me", "kcalloc")
        self.assertIsNone(self.run_hook("/migrate kcalloc"))

    def test_no_holder_gives_the_title(self):
        out = self.run_hook("/migrate kcalloc")
        self.assertEqual(out["sessionTitle"], "kcalloc")

    def test_the_plugin_form_gives_the_title(self):
        out = self.run_hook("/session-crew:migrate kcalloc")
        self.assertEqual(out["sessionTitle"], "kcalloc")

    def test_dead_holder_counts_as_no_holder(self):
        self.session(2147480000, "old", "kcalloc", "idle")
        self.assertEqual(self.run_hook("/migrate kcalloc")["sessionTitle"], "kcalloc")

    def test_holder_in_another_folder_is_ignored(self):
        proc = self.child(["sleep", "60"])
        self.session(proc.pid, "old", "kcalloc", "idle", cwd="/other/dir")
        self.assertEqual(self.run_hook("/migrate kcalloc")["sessionTitle"], "kcalloc")
        self.assertIsNone(proc.poll())

    def test_idle_holder_is_terminated_then_title(self):
        proc = self.child(["sleep", "60"])
        out = self.run_hook("/migrate kcalloc")
        self.assertEqual(out["sessionTitle"], "kcalloc")
        proc.wait(timeout=5)
        self.assertEqual(proc.returncode, -signal.SIGTERM)

    def test_busy_holder_is_not_signalled(self):
        for status in ("busy", "waiting"):
            proc = self.child(["sleep", "60"], status=status)
            out = self.run_hook("/migrate kcalloc")
            self.assertNotIn("sessionTitle", out)
            self.assertIn("busy or waiting", out["additionalContext"])
            self.assertIsNone(proc.poll())

    def test_holder_that_ignores_sigterm_gets_no_title(self):
        self.child("trap '' TERM; sleep 60")
        time.sleep(0.5)  # let the shell install its trap
        with unittest.mock.patch.object(rename, "WAIT_S", 0.5):
            out = self.run_hook("/migrate kcalloc")
        self.assertNotIn("sessionTitle", out)
        self.assertIn("did not stop", out["additionalContext"])

    def test_own_session_is_never_the_holder(self):
        self.session(os.getpid(), "me", "kcalloc")  # same sessionId as the event
        self.assertEqual(registry.holders("kcalloc", CWD, "me"), [])
