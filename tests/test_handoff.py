import os
import subprocess
import sys

from helpers import CWD, CrewCase, ROOT, SLUG

import handoff
import migrate
import registry

CREW = os.path.join(ROOT, "scripts", "crew.py")
BODY = "\n".join(h + "\ntext of " + h for h in handoff.SECTIONS)


class Save(CrewCase):
    def test_refuses_each_missing_section(self):
        for i, heading in enumerate(handoff.SECTIONS):
            body = "\n".join(h + "\nx" for j, h in enumerate(handoff.SECTIONS) if j != i)
            with self.assertRaises(ValueError) as cm:
                handoff.save(registry.Identity("a", "12345678", CWD), body)
            self.assertIn(heading, str(cm.exception))
        self.assertEqual(handoff.pending(CWD), [])

    def test_refuses_sections_out_of_order(self):
        body = "\n".join(h + "\nx" for h in reversed(handoff.SECTIONS))
        with self.assertRaises(ValueError):
            handoff.save(registry.Identity("a", "12345678", CWD), body)

    def test_writes_front_matter_and_name(self):
        path = handoff.save(registry.Identity("alpha", "abcdef0123", CWD), BODY)
        meta, body = handoff.parse(path)
        self.assertEqual((meta["status"], meta["name"], meta["cwd"], meta["session_id"]),
                         ("pending", "alpha", CWD, "abcdef0123"))
        self.assertRegex(os.path.basename(path), r"^\d{8}T\d{6}Z-abcdef01\.md$")
        self.assertIn("text of ## What remains", body)

    def test_unnamed_session(self):
        path = handoff.save(registry.Identity(None, "abcdef0123", CWD), BODY)
        self.assertEqual(os.path.basename(os.path.dirname(path)), "unnamed-abcdef01")

    def test_command_line_identity_by_parent_pid(self):
        self.session(os.getpid(), "feedface00", "alpha")
        r = subprocess.run([sys.executable, "-I", CREW, "handoff", "save"], input=BODY,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(r.stdout.strip().endswith("-feedface.md"))
        self.assertIn("/alpha/", r.stdout)
        r = subprocess.run([sys.executable, "-I", CREW, "handoff", "status"],
                           capture_output=True, text=True)
        self.assertIn("alpha", r.stdout)

    def test_command_line_refuses_missing_section(self):
        r = subprocess.run([sys.executable, "-I", CREW, "handoff", "save", "--name", "a",
                            "--cwd", CWD, "--session-id", "12345678"], input="## What remains\n",
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("missing the section", r.stderr)

    def test_flags_override_registry(self):
        self.session(os.getpid(), "feedface00", "alpha")
        r = subprocess.run([sys.executable, "-I", CREW, "handoff", "save", "--name", "beta",
                            "--session-id", "cafe0000", "--cwd", "/o/p"], input=BODY,
                           capture_output=True, text=True)
        self.assertIn("-o-p/beta/", r.stdout)


class Supersede(CrewCase):
    def test_new_save_supersedes_earlier_ones_of_the_same_name_only(self):
        old1 = self.pending("alpha", sid="11111111")
        old2 = self.pending("alpha", sid="22222222")
        other = self.pending("beta", sid="33333333")
        new = self.pending("alpha", sid="44444444")
        meta, _ = handoff.parse(old2)
        self.assertEqual((meta["status"], meta["superseded_by"]),
                         ("superseded", os.path.basename(new)))
        self.assertEqual(handoff.parse(old1)[0]["status"], "superseded")
        self.assertEqual(handoff.parse(other)[0]["status"], "pending")
        self.assertEqual([p for p, _ in handoff.pending(CWD, "alpha")], [new])

    def test_refused_save_supersedes_nothing(self):
        old = self.pending("alpha")
        with self.assertRaises(ValueError):
            handoff.save(registry.Identity("alpha", "55555555", CWD), "## What remains\n")
        self.assertEqual(handoff.parse(old)[0]["status"], "pending")


class Migrate(CrewCase):
    def ident(self, name="alpha", sid="newsess00"):
        return registry.Identity(name, sid, CWD)

    def test_prints_marks_used_and_never_repicks(self):
        self.project(sessions=[{"name": "alpha", "role": "the alpha role", "owns": ["x"]}])
        path = self.pending("alpha")
        rc, _, raw = self.call(migrate.run, self.ident(), None)
        self.assertEqual(rc, 0)
        self.assertIn("## What remains\nx", raw)
        self.assertIn("the alpha role", raw)
        meta, _ = handoff.parse(path)
        self.assertEqual((meta["status"], meta["used_by"]), ("used", "newsess00"))
        self.assertIn("used_at", meta)
        self.assertEqual(handoff.pending(CWD), [])
        _, _, raw = self.call(migrate.run, self.ident(), None)
        self.assertIn("No pending handoff", raw)
        self.assertNotIn("## Work under way", raw)

    def test_picks_the_latest_pending(self):
        old = self.pending("alpha", sid="11111111")
        new = self.pending("alpha", sid="22222222")
        self.call(migrate.run, self.ident(), None)
        self.assertEqual(handoff.parse(new)[0]["status"], "used")
        self.assertEqual(handoff.parse(old)[0]["status"], "superseded")

    def test_names_a_live_holder_first(self):
        self.pending("alpha")
        proc = subprocess.Popen(["sleep", "60"])
        self.addCleanup(lambda: (proc.kill(), proc.wait()))
        self.session(proc.pid, "oldsess00", "alpha", "busy")
        self.transcript("oldsess00", 3)
        _, _, raw = self.call(migrate.run, self.ident(), None)
        self.assertTrue(raw.startswith("NOTE: a live session called alpha"))
        self.assertIn("status busy", raw)
        self.assertIn("transcript 3 MB", raw)

    def test_unnamed_session_takes_the_latest_of_the_folder(self):
        self.pending("alpha")
        _, _, raw = self.call(migrate.run, self.ident(name=None), None)
        self.assertIn("## Work under way", raw)


class StartHook(CrewCase):
    def event(self, source, sid="new1", name="alpha"):
        self.session(100, sid, name) if name else None
        return {"session_id": sid, "cwd": CWD, "source": source}

    def test_clear_with_pending_tells_both(self):
        self.pending("alpha")
        _, out, _ = self.call(migrate.hook_start, self.event("clear"))
        self.assertIn("Passaggio in attesa per alpha: scrivi /migrate.", out["systemMessage"])
        self.assertIn("alpha", out["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "SessionStart")

    def test_startup_works_too_resume_does_not(self):
        self.pending("alpha")
        self.assertIsNotNone(self.call(migrate.hook_start, self.event("startup"))[1])
        self.assertIsNone(self.call(migrate.hook_start, self.event("resume"))[1])

    def test_no_pending_is_silent(self):
        self.assertIsNone(self.call(migrate.hook_start, self.event("clear"))[1])

    def test_unnamed_session_gets_the_folder_and_the_name(self):
        self.pending("alpha")
        _, out, _ = self.call(migrate.hook_start, self.event("clear", name=None))
        self.assertIn("scrivi /migrate alpha.", out["systemMessage"])

    def test_used_handoff_is_not_announced(self):
        handoff.mark_used(self.pending("alpha"), "x")
        self.assertIsNone(self.call(migrate.hook_start, self.event("clear"))[1])
