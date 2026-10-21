"""Subprocess runs of the hooks, the rename guard's edge cases, recover budgets, manifests."""
import json
import os
import signal
import subprocess
import sys
import unittest.mock

from helpers import CWD, CrewCase, MB, ROOT

import config
import recover
import registry

CREW = os.path.join(ROOT, "scripts", "crew.py")


def run_hook(which, event):
    r = subprocess.run([sys.executable, "-I", CREW, "hook", which], input=json.dumps(event),
                       capture_output=True, text=True, env=dict(os.environ))
    out = json.loads(r.stdout) if r.stdout.strip() else None
    return r.returncode, out, r.stderr


class Procs(CrewCase):
    def sleeper(self):
        proc = subprocess.Popen(["sleep", "60"], start_new_session=True)

        def reap():
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()
        self.addCleanup(reap)
        return proc

    @staticmethod
    def reap(proc):
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        proc.wait()

    def raw_session(self, filename, **fields):
        entry = dict({"sessionId": "old", "cwd": CWD, "name": "kcalloc", "status": "idle"},
                     **fields)
        with open(os.path.join(self.claude, "sessions", filename), "w") as f:
            json.dump(entry, f)


class RenameSubprocess(Procs):
    def setUp(self):
        super().setUp()
        self.session(100, "me", "newtab")
        self.pending("kcalloc")

    def rename(self, prompt):
        rc, out, err = run_hook("rename", {"session_id": "me", "cwd": CWD, "prompt": prompt})
        self.assertEqual(rc, 0, err)
        return (out or {}).get("hookSpecificOutput")

    def test_exact_prompt_works_through_the_entry_point(self):
        self.assertEqual(self.rename("/migrate kcalloc")["sessionTitle"], "kcalloc")

    def test_tabs_and_double_spaces_do_nothing(self):
        for prompt in ["/migrate\tkcalloc", "/migrate  kcalloc", " /migrate kcalloc ".replace(
                "/migrate ", "/migrate  ")]:
            self.assertIsNone(self.rename(prompt), repr(prompt))

    def test_junk_pids_are_never_holders(self):
        proc = self.sleeper()
        self.raw_session("zero.json", pid=0)
        self.raw_session("one.json", pid=1)
        self.raw_session("true.json", pid=True)
        self.raw_session("str.json", pid=str(proc.pid))
        self.assertEqual(self.rename("/migrate kcalloc")["sessionTitle"], "kcalloc")
        self.assertIsNone(proc.poll())

    def test_same_pid_as_the_session_with_another_session_id(self):
        proc = self.sleeper()
        self.session(proc.pid, "me", "newtab")
        self.raw_session("other.json", pid=proc.pid,
                         procStart=registry.proc_start(proc.pid))
        self.assertEqual(self.rename("/migrate kcalloc")["sessionTitle"], "kcalloc")
        self.assertIsNone(proc.poll())

    def test_procstart_mismatch_means_the_session_is_gone(self):
        proc = self.sleeper()
        self.session(proc.pid, "old", "kcalloc", "idle", started="Mon Jan  1 00:00:00 2001")
        self.assertEqual(self.rename("/migrate kcalloc")["sessionTitle"], "kcalloc")
        self.assertIsNone(proc.poll())

    def test_procstart_whitespace_is_normalised(self):
        proc = self.sleeper()
        real = registry.proc_start(proc.pid)
        self.session(proc.pid, "old", "kcalloc", "idle", started="  " + real.replace(" ", "   "))
        out = self.rename("/migrate kcalloc")
        proc.wait(timeout=5)
        self.assertEqual(out["sessionTitle"], "kcalloc")

    def test_missing_procstart_is_never_signalled_nor_replaced(self):
        proc = self.sleeper()
        self.session(proc.pid, "old", "kcalloc", "idle", started=None)
        out = self.rename("/migrate kcalloc")
        self.assertNotIn("sessionTitle", out)
        self.assertIn("could not be verified", out["additionalContext"])
        self.assertIsNone(proc.poll())

    def test_several_idle_holders_all_stop(self):
        procs = [self.sleeper() for _ in range(3)]
        for i, p in enumerate(procs):
            self.session(p.pid, "old%d" % i, "kcalloc", "idle")
        out = self.rename("/migrate kcalloc")
        self.assertEqual(out["sessionTitle"], "kcalloc")
        for p in procs:
            p.wait(timeout=5)
            self.assertEqual(p.returncode, -signal.SIGTERM)

    def test_one_shared_wait_for_several_holders(self):
        import rename
        stubborn = [subprocess.Popen(["sh", "-c", "trap '' TERM; while :; do sleep 1; done"],
                                    start_new_session=True)
                    for _ in range(3)]
        for p in stubborn:
            self.addCleanup(self.reap, p)
        import time
        time.sleep(0.5)  # let each shell install its trap
        with unittest.mock.patch.object(rename, "WAIT_S", 1.0):
            t = time.monotonic()
            left = rename._stop_all([p.pid for p in stubborn])
            took = time.monotonic() - t
        self.assertEqual(len(left), 3)
        self.assertLess(took, 2.0)


class SizeAndStartSubprocess(Procs):
    def test_size_hook_by_stdin(self):
        self.session(100, "s1", "alpha")
        path = self.transcript("s1", 450)
        rc, out, _ = run_hook("size", {"session_id": "s1", "cwd": CWD,
                                       "transcript_path": path, "prompt": "x"})
        self.assertEqual(rc, 0)
        self.assertIn("/handoff", out["hookSpecificOutput"]["additionalContext"])

    def test_start_hook_by_stdin(self):
        self.project()
        self.session(100, "s2", "alpha")
        self.pending("alpha")
        rc, out, _ = run_hook("start", {"session_id": "s2", "cwd": CWD, "source": "clear"})
        self.assertEqual(rc, 0)
        self.assertIn("scrivi /migrate", out["systemMessage"])

    def test_night_start_wins_when_the_mode_is_already_full(self):
        self.session(100, "s1", "alpha")
        self.project(unattended={"status_command": ["sh", "-c", "echo mode: full"],
                                 "active_pattern": "^mode: full",
                                 "start_prefixes": ["vai in modalità full"], "ceiling_mb": 1000})
        path = self.transcript("s1", 450)
        rc, out, _ = run_hook("size", {"session_id": "s1", "cwd": CWD, "transcript_path": path,
                                       "prompt": "Vai in modalità full"})
        self.assertIn("prima della notte", out["systemMessage"])

    def test_partial_unattended_config(self):
        self.session(100, "s1", "alpha")
        self.project(unattended={"start_prefixes": ["go"]})
        path = self.transcript("s1", 450)
        rc, out, err = run_hook("size", {"session_id": "s1", "cwd": CWD,
                                         "transcript_path": path, "prompt": "go tonight"})
        self.assertEqual(rc, 0, err)
        self.assertIn("prima della notte", out["systemMessage"])
        rc, out, err = run_hook("size", {"session_id": "s1", "cwd": CWD,
                                         "transcript_path": path, "prompt": "hello"})
        self.assertEqual(rc, 0, err)
        self.assertIn("/handoff", out["hookSpecificOutput"]["additionalContext"])

    def test_unattended_as_junk_is_ignored(self):
        self.session(100, "s1", "alpha")
        self.project(unattended="yes", warn_mb=1)
        path = self.transcript("s1", 5)
        rc, out, err = run_hook("size", {"session_id": "s1", "cwd": CWD,
                                         "transcript_path": path, "prompt": "x"})
        self.assertEqual(rc, 0, err)


