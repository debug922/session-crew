"""Shared fixtures: every case runs in temporary folders reached through the two env vars."""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import unittest.mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

CWD = "/work/proj"
SLUG = "-work-proj"
MB = 1024 * 1024


class CrewCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="crew-test-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.crew_home = os.path.join(self.tmp, "crew")
        self.claude = os.path.join(self.tmp, "claude")
        os.makedirs(os.path.join(self.claude, "sessions"))
        os.makedirs(os.path.join(self.claude, "projects", SLUG))
        patch = unittest.mock.patch.dict(os.environ, {
            "SESSION_CREW_HOME": self.crew_home, "CLAUDE_CONFIG_DIR": self.claude})
        patch.start()
        self.addCleanup(patch.stop)

    def project(self, **cfg):
        folder = os.path.join(self.crew_home, SLUG)
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "project.json"), "w") as f:
            json.dump(cfg, f)

    def session(self, pid, sid, name="alpha", status="idle", cwd=CWD):
        with open(os.path.join(self.claude, "sessions", "%d.json" % pid), "w") as f:
            json.dump({"pid": pid, "sessionId": sid, "cwd": cwd, "name": name,
                       "nameSource": "user", "status": status, "updatedAt": 0}, f)

    def transcript(self, sid, mb=0, lines=None):
        path = os.path.join(self.claude, "projects", SLUG, sid + ".jsonl")
        with open(path, "wb") as f:
            if lines:
                f.write(("\n".join(json.dumps(x) for x in lines) + "\n").encode())
            f.truncate(max(f.tell(), int(mb * MB)))
        return path

    def pending(self, name="alpha", sid="aaaaaaaa-1111", cwd=CWD):
        import handoff
        from registry import Identity
        body = "\n".join(h + "\nx" for h in handoff.SECTIONS)
        return handoff.save(Identity(name, sid, cwd), body)

    def call(self, fn, *args):
        """Run fn(*args) and return (return value, parsed JSON of stdout or None, raw stdout)."""
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = fn(*args)
        raw = out.getvalue()
        return rc, (json.loads(raw) if raw.strip().startswith("{") else None), raw
