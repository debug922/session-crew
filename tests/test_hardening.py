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


def msg(kind, text):
    return {"type": kind, "message": {"content": text}}


class RecoverBudgets(CrewCase):
    def ident(self):
        return registry.Identity("alpha", "mine0000", CWD)

    def test_summary_survives_a_huge_tail(self):
        summary = "BEGIN" + "s" * 30000 + "END"
        lines = [{"type": "custom-title", "customTitle": "alpha"},
                 dict(msg("user", summary), isCompactSummary=True)]
        lines += [msg("user" if i % 2 else "assistant", "t%d " % i + "x" * 1000)
                  for i in range(150)]
        self.transcript("old00000", lines=lines)
        with unittest.mock.patch.object(recover, "CHUNK", 4096):
            _, _, raw = self.call(recover.run, self.ident(), "alpha")
        self.assertIn(summary, raw)
        self.assertIn("t149 ", raw)
        self.assertNotIn("t0 ", raw)

    def test_summary_is_cut_at_40k(self):
        lines = [{"type": "custom-title", "customTitle": "alpha"},
                 dict(msg("user", "s" * 50000), isCompactSummary=True)]
        self.transcript("old00000", lines=lines)
        _, _, raw = self.call(recover.run, self.ident(), "alpha")
        self.assertIn("s" * recover.TOTAL_CUT, raw)
        self.assertNotIn("s" * (recover.TOTAL_CUT + 1), raw)

    def test_one_budget_for_the_whole_run(self):
        for i in range(5):
            lines = [{"type": "custom-title", "customTitle": "other"}]
            lines += [msg("user", "p" * 1000)] * 1000  # about 1 MB after the title
            path = self.transcript("c000000%d" % i, lines=lines)
            os.utime(path, (10 + i, 10 + i))
        made = []

        class Counting(recover.Budget):
            def __init__(self, left):
                super().__init__(left)
                self.total, self.spent = left, 0
                made.append(self)

            def spend(self, n):
                self.spent += n
                super().spend(n)

        with unittest.mock.patch.object(recover, "Budget", Counting), \
                unittest.mock.patch.object(recover, "MAX_READ", 2 * MB), \
                unittest.mock.patch.object(recover, "MAX_TITLE", 10 * MB), \
                unittest.mock.patch.object(recover, "CHUNK", 64 * 1024):
            self.call(recover.run, self.ident(), "alpha")
        self.assertEqual(len(made), 1)
        self.assertLessEqual(made[0].spent, 2 * MB)
        self.assertGreater(made[0].spent, MB)

    def test_title_scan_is_capped_per_candidate(self):
        lines = [{"type": "custom-title", "customTitle": "alpha"}] + [msg("user", "p" * 1000)] * 500
        path = self.transcript("old00000", lines=lines)
        with unittest.mock.patch.object(recover, "MAX_TITLE", 100 * 1024):
            self.assertIsNone(recover.last_title(path, recover.Budget(10 * MB)))

    def test_overlong_line_is_dropped(self):
        path = os.path.join(self.tmp, "f")
        lines = ["a%d" % i for i in range(50)] + ["B" * 10000] + ["c%d" % i for i in range(50)]
        with open(path, "w") as f:
            f.write("\n".join(lines) + "\n")
        with unittest.mock.patch.object(recover, "MAX_LINE", 500):
            for chunk in (64, 300, 5000):
                got = [x.decode() for x in recover.reverse_lines(path, recover.Budget(10**9),
                                                                 chunk=chunk)]
                self.assertEqual(got, [l for l in lines if l[0] != "B"][::-1], chunk)


class Slug(CrewCase):
    def test_every_non_alphanumeric_becomes_a_dash(self):
        cwd = "/Users/x y/my_proj.v2"
        self.assertEqual(config.slug(cwd), "-Users-x-y-my-proj-v2")

    def test_transcripts_found_under_the_slug(self):
        cwd = "/Users/x y/my_proj.v2"
        folder = os.path.join(self.claude, "projects", config.slug(cwd))
        os.makedirs(folder)
        with open(os.path.join(folder, "old00000.jsonl"), "w") as f:
            f.write(json.dumps({"type": "custom-title", "customTitle": "alpha"}) + "\n"
                    + json.dumps(msg("user", "HELLO")) + "\n")
        _, _, raw = self.call(recover.run, registry.Identity("alpha", "me", cwd), "alpha")
        self.assertIn("HELLO", raw)

    def test_long_cwd_globs_the_prefix_with_the_hash(self):
        cwd = "/" + "/".join("dir%d" % i for i in range(60))
        self.assertGreater(len(config.raw_slug(cwd)), 200)
        self.assertEqual(len(config.slug(cwd)), 200)
        folder = os.path.join(self.claude, "projects", config.slug(cwd) + "-8f3a2b")
        os.makedirs(folder)
        with open(os.path.join(folder, "abc12345.jsonl"), "w") as f:
            f.write("{}\n")
        self.assertEqual(config.transcript_path(cwd, "abc12345"),
                         os.path.join(folder, "abc12345.jsonl"))

    def test_crew_folder_uses_the_same_slug(self):
        cwd = "/a b/c_d.e"
        self.assertEqual(config.project_dir(cwd), os.path.join(self.crew_home, "-a-b-c-d-e"))


class Manifests(unittest.TestCase):
    def load(self, *parts):
        with open(os.path.join(ROOT, *parts)) as f:
            return json.load(f)

    def test_plugin_and_marketplace(self):
        plugin = self.load(".claude-plugin", "plugin.json")
        self.assertEqual((plugin["name"], plugin["version"]), ("session-crew", "0.1.0"))
        market = self.load(".claude-plugin", "marketplace.json")
        self.assertEqual(market["name"], "session-crew")
        self.assertEqual([(p["name"], p["source"]) for p in market["plugins"]],
                         [("session-crew", "./")])

    def test_hooks(self):
        hooks = self.load("hooks", "hooks.json")["hooks"]
        prompt = hooks["UserPromptSubmit"][0]["hooks"]
        self.assertEqual([(h["type"], h["timeout"]) for h in prompt],
                         [("command", 10), ("command", 15)])
        self.assertTrue(prompt[0]["command"].endswith('crew.py" hook size'))
        self.assertTrue(prompt[1]["command"].endswith('crew.py" hook rename'))
        start = hooks["SessionStart"][0]
        self.assertEqual(start["matcher"], "startup|clear")
        self.assertEqual(start["hooks"][0]["timeout"], 10)
        for h in prompt + start["hooks"]:
            self.assertTrue(h["command"].startswith('python3 -I "${CLAUDE_PLUGIN_ROOT}/'))
