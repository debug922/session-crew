"""A world for the guard tests: a project folder with a table of three repositories, a repository
outside the table, a worktree of one of them, and sessions in a fake registry."""
import json
import os
import subprocess
import sys

from helpers import CrewCase

import guard
import project

FULL = {"status_command": [sys.executable, "-c", "print('mode: night')"], "active_pattern": "^mode: night"}
IDLE = {"status_command": [sys.executable, "-c", "print('mode: day')"], "active_pattern": "^mode: night"}


def sh(cwd, *args):
    subprocess.run(args, cwd=cwd, check=True, capture_output=True)


class GuardCase(CrewCase):
    def setUp(self):
        super().setUp()
        self.work = os.path.join(os.path.realpath(self.tmp), "work")
        self.plugin = guard.ROOT
        self.door = 'python3 -I "%s" ' % guard.CREW
        for rel in ("core", "lib", "site", "other"):
            os.makedirs(os.path.join(self.work, rel))
            sh(os.path.join(self.work, rel), "git", "init", "-q", "-b", "main")
        sh(self.work + "/core", "git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
           "--allow-empty", "-m", "Start")
        self.wt = os.path.join(self.work, "wt")
        os.makedirs(os.path.join(self.work, "plain"))
        sh(self.work + "/core", "git", "worktree", "add", "-q", "--detach", self.wt)
        self.entries = [self.entry("core", ["boss"], tags={"version": "changelog", "annotated": False}),
                        self.entry("lib", ["boss", "helper"]),
                        self.entry("site", ["boss"], visibility="public")]
        self.table()
        self.session(100, "s-boss", "boss", cwd=self.work)

    def entry(self, name, pushers, visibility="private", tags=None):
        return {"name": name, "path": os.path.join(self.work, name), "github": "o/" + name,
                "visibility": visibility, "pushers": pushers, "checks": [], "tags": tags}

    def table(self, entries=None, **extra):
        project.write(self.work, dict({"repos": self.entries if entries is None else entries}, **extra))

    def night(self, on=True):
        self.table(self.entries, unattended=FULL if on else IDLE)

    def bash(self, cmd, sid="s-boss", cwd=None, **extra):
        """The decision kind ("allow-less": None when the guard says nothing) for a Bash event."""
        event = {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": cwd or self.work,
                 "session_id": sid, **extra}
        return self.decide(guard.run_bash, event)

    def files(self, tool, sid="s-boss", cwd=None, **ti):
        event = {"tool_name": tool, "tool_input": ti, "cwd": cwd or self.work, "session_id": sid}
        return self.decide(guard.run_files, event)

    def decide(self, fn, event):
        rc, out, raw = self.call(fn, json.dumps(event))
        self.assertEqual(rc, 0, raw)
        return out["hookSpecificOutput"]["permissionDecision"] if out else None
