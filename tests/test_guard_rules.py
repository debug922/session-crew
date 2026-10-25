"""The rest of the Bash guard: git push and tag, deletes on a remote, GitHub, the configuration,
the night, and a folder with no project file."""
import os

from guardhelp import GuardCase

import config
import guard
import project

PUSHES = ["git push", "git push origin main", "git push -u origin main", "git push --tags",
          "git push -o ci.skip origin main", "git push origin main:main"]
DELETES = ["git push --force", "git push -f origin main", "git push --force-with-lease",
           "git push --force-with-lease=main:abc origin main", "git push origin --delete fix/x",
           "git push -d origin fix/x", "git push origin :fix/x", "git push origin +main",
           "git push --mirror", "git push --prune origin", "git -C lib push -fu origin main",
           "git push origin :refs/tags/v0.1.0"]
GITHUB = ["gh repo delete o/x --yes", "gh release delete v1", "gh release delete-asset v1 a",
          "gh api -X DELETE repos/o/x/git/refs/heads/y", "gh api --method DELETE /repos/o/x",
          "gh api -XDELETE /repos/x", "curl -s -X DELETE https://api.github.com/repos/o/x",
          "curl --request DELETE https://api.github.com/repos/o/x"]
MACHINE = ["git branch -D fix/x", "git reset --hard HEAD~1", "git worktree remove --force /x",
           "git tag -l", "git tag --list 'v*'", "rm -rf build", "gh repo view o/x", "gh pr list",
           "curl -X DELETE http://localhost:8080/v1/x", "git stash drop"]


class Pushes(GuardCase):
    def test_a_plain_push_in_a_table_repository_points_at_the_door(self):
        for cmd in PUSHES:
            self.assertEqual(self.bash(cmd, cwd=self.work + "/core"), "deny", cmd)
        self.assertEqual(self.bash("git -C core push", cwd=self.work), "deny")
        self.assertEqual(self.bash("git push", cwd=self.wt), "deny")  # a worktree of a table repository

    def test_a_push_that_cannot_be_placed_is_denied(self):
        for cmd, cwd in [("git push", self.work), ("git push", self.work + "/plain"),
                         ("cd other && git push", self.work), ("git --git-dir=other/.git push", self.work)]:
            self.assertEqual(self.bash(cmd, cwd=cwd), "deny", cmd)

    def test_a_push_in_a_repository_outside_the_table_is_left_to_the_user(self):
        self.assertIsNone(self.bash("git push", cwd=self.work + "/other"))
        self.assertIsNone(self.bash("git -C other push origin main", cwd=self.work))

    def test_a_project_without_a_table_leaves_pushes_alone(self):
        self.table([])
        self.assertIsNone(self.bash("git push", cwd=self.work + "/core"))
        project.write(self.work, {"lang": "en"})
        self.assertIsNone(self.bash("git push", cwd=self.work + "/core"))

    def test_a_tag_in_a_table_repository_is_refused_and_listing_is_not(self):
        for cmd in ["git tag v0.1.0", "git tag -a v0.1.0 -m x", "git tag -d v0.1.0"]:
            self.assertEqual(self.bash(cmd, cwd=self.work + "/core"), "deny", cmd)
        self.assertIsNone(self.bash("git tag -l", cwd=self.work + "/core"))
        self.assertIsNone(self.bash("git tag v0.1.0", cwd=self.work + "/other"))
        self.assertEqual(self.bash("gh release create v1", cwd=self.work + "/core"), "deny")
        self.assertEqual(self.bash("gh release create v1 -R o/lib", cwd=self.work + "/other"), "deny")
        self.assertIsNone(self.bash("gh release create v1 -R o/else", cwd=self.work + "/core"))
        self.assertIsNone(self.bash("gh release create v1", cwd=self.work + "/other"))


class Deletes(GuardCase):
    def test_the_project_is_found_from_a_subfolder_of_the_events_folder(self):
        self.assertEqual(self.bash("git push --force", cwd=self.work + "/core/deeper/still"), "ask")
        # The project is the event's folder, as the door's is the process's: never the registry's.
        self.assertIsNone(self.bash("git push --force", cwd="/elsewhere"))

    def test_a_push_that_deletes_or_rewrites_on_the_remote_asks_anywhere_in_a_project(self):
        for cmd in DELETES:
            self.assertEqual(self.bash(cmd), "ask", cmd)
        self.assertEqual(self.bash("git push --force", cwd=self.work + "/other"), "ask")

    def test_a_delete_on_github_asks(self):
        for cmd in GITHUB:
            self.assertEqual(self.bash(cmd), "ask", cmd)

    def test_at_night_they_are_refused(self):
        self.night(True)
        for cmd in ["git push --force", "gh repo delete o/x", "git push origin :x"]:
            self.assertEqual(self.bash(cmd), "deny", cmd)
        self.night(False)
        self.assertEqual(self.bash("git push --force"), "ask")

    def test_deletes_on_the_machine_are_not_this_guards(self):
        for cmd in MACHINE:
            self.assertIsNone(self.bash(cmd, cwd=self.work + "/other"), cmd)


class Configuration(GuardCase):
    def setUp(self):
        super().setUp()
        self.file = config.project_file(self.work)

    def crew(self, rest):
        return 'python3 -I "%s" %s' % (guard.CREW, rest)

    def test_config_apply_asks_by_day_and_is_refused_at_night(self):
        self.assertEqual(self.bash(self.crew("config apply d.json")), "ask")
        self.assertEqual(self.bash(self.crew("config apply d.json --cwd /tmp/x")), "ask")
        # A copy of the script elsewhere is not the plugin's own path: refused, not asked.
        self.assertEqual(self.bash("python3 -I /tmp/copy/crew.py config apply d.json"), "deny")
        self.night(True)
        self.assertEqual(self.bash(self.crew("config apply d.json")), "deny")

    def test_other_ways_to_write_the_project_file_ask(self):
        for cmd in ["echo {} > %s" % self.file, "cp t.json %s" % self.file,
                    "sed -i '' s/a/b/ %s" % self.file, "echo {} >> ~/.session-crew/-x-y/project.json",
                    "cp t.json $HOME/.session-crew/-x-y/project.json", "rm %s" % self.file]:
            self.assertEqual(self.bash(cmd), "ask", cmd)
        self.night(True)
        self.assertEqual(self.bash("echo {} > %s" % self.file), "deny")

    def test_writing_into_the_plugins_folder_asks(self):
        for cmd in ["echo x > %s/hooks/hooks.json" % guard.ROOT, "rm -r %s" % guard.ROOT,
                    "cp x.md %s/README.md" % guard.ROOT]:
            self.assertEqual(self.bash(cmd), "ask", cmd)
        # Anything naming the scripts that is not an allowed shape or a plain read is refused.
        for cmd in ["cp x.py %s/scripts/guard.py" % guard.ROOT,
                    "sed -i '' s/a/b/ %s/scripts/door.py" % guard.ROOT]:
            self.assertEqual(self.bash(cmd), "deny", cmd)

    def test_reading_the_file_running_the_plugin_or_writing_a_draft_passes(self):
        for cmd in ["cat %s" % self.file, "jq . %s >/dev/null" % self.file, "ls %s/scripts" % guard.ROOT,
                    self.crew("config discover"), self.crew("config show"),
                    self.crew("handoff save <<'H'\n## Work under way\nH"), self.crew("migrate"),
                    "grep -n push %s/scripts/door.py" % guard.ROOT]:
            self.assertIsNone(self.bash(cmd), cmd)


class NoProject(GuardCase):
    def setUp(self):
        super().setUp()
        self.file = config.project_file(self.work)
        os.remove(self.file)

    def test_the_git_rules_say_nothing_in_a_folder_with_no_project_file(self):
        cmds = PUSHES + DELETES + GITHUB + ["git tag v1", "gh release create v1", self.door + "push lib"]
        for cmd in cmds:
            self.assertIsNone(self.bash(cmd, cwd=self.work + "/core"), cmd)

    def test_the_file_that_grants_pushes_is_guarded_before_it_exists(self):
        for cmd in [self.door + "config apply d.json", "echo {} > %s" % self.file,
                    "cp t.json %s" % self.file, "tee %s" % self.file,
                    "cp t.json ~/.session-crew/-x-y/project.json",
                    "cp x.py %s/scripts/guard.py" % guard.ROOT]:
            self.assertEqual(self.bash(cmd, cwd=self.work + "/core"), "ask", cmd)
        self.assertEqual(self.files("Write", file_path=self.file, content="{}"), "ask")
        self.assertEqual(self.files("Write", file_path=guard.ROOT + "/scripts/door.py"), "ask")
        self.assertIsNone(self.files("Write", file_path=self.work + "/a.txt", content="x"))

    def test_and_a_session_cannot_grant_itself_the_door(self):
        self.assertEqual(self.bash(self.door + "push lib"), None)  # no table, no guard; the door refuses
        self.assertEqual(self.bash("echo '{\"repos\": []}' > " + self.file), "ask")


class Wiring(GuardCase):
    def test_the_hooks_run_as_the_plugin_declares_them(self):
        import json
        import subprocess
        import sys
        with open(os.path.join(guard.ROOT, "hooks", "hooks.json")) as f:
            declared = json.load(f)["hooks"]["PreToolUse"]
        self.assertEqual([d["matcher"] for d in declared], ["Bash", "Edit|MultiEdit|Write|NotebookEdit"])
        self.assertEqual(len(declared[0]["hooks"]), 1)
        event = {"tool_name": "Bash", "tool_input": {"command": "git push --force"}, "cwd": self.work,
                 "session_id": "s-boss"}
        for which, want in (("guard-bash", "ask"), ("guard-files", None)):
            out = subprocess.run([sys.executable, "-I", os.path.join(guard.ROOT, "scripts", "crew.py"),
                                  "hook", which], input=json.dumps(event), capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stderr)
            got = json.loads(out.stdout)["hookSpecificOutput"]["permissionDecision"] if out.stdout else None
            self.assertEqual(got, want, which)
            self.assertIn("hook %s" % which, declared[0]["hooks"][0]["command"] + declared[1]["hooks"][0]["command"])
