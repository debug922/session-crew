"""Claude Code's registry of sessions is what the door and the guard take as proof of a name: no
tool of a session writes it, in a configured folder or not."""
import json
import os

from guardhelp import GuardCase

import config
import guard


class Registry(GuardCase):
    def setUp(self):
        super().setUp()
        self.s = os.path.join(self.claude, "sessions")
        self.link = os.path.join(self.work, "lnk")
        os.symlink(self.s, self.link)

    def both(self, fn, expect):
        """The same check in the configured folder and, the project file gone, in an unconfigured one."""
        fn(expect)
        if os.path.exists(config.project_file(self.work)):
            os.remove(config.project_file(self.work))
        fn(expect)

    def test_a_write_into_the_sessions_folder_is_refused_in_every_form(self):
        s, c = self.s, self.claude
        cmds = ["echo x > %s/1.json" % s, "echo x >> %s/1.json" % s, "echo x >| %s/1.json" % s,
                "echo x &> %s/1.json" % s, "cp /tmp/x %s/1.json" % s, "cp -t %s /tmp/x" % s,
                "install /tmp/x %s/1.json" % s, "tee %s/1.json" % s, "mv /tmp/x %s/1.json" % s,
                "rm %s/100.json" % s, "rm -rf %s" % s, "sed -i '' s/a/b/ %s/100.json" % s,
                "ln -s /tmp/x %s/1.json" % s, "ln -sfn /tmp/evil %s" % s, "mv %s /tmp/gone" % s,
                "mv %s /tmp/gone" % c, "rm -rf %s" % c, "ln -sfn /tmp/evil %s" % c,
                "cd %s && echo x > 1.json" % s, "cd %s; tee 1.json" % s, "pushd %s && cp /tmp/x ." % s,
                "D=%s; echo x > $D/1.json" % s, "export C=%s; echo x > $C/sessions/1.json" % c,
                "echo x > $CLAUDE_CONFIG_DIR/sessions/1.json", "echo x > ${CLAUDE_CONFIG_DIR}/sessions/1.json",
                "echo x > ~/.claude/sessions/1.json", "echo x > lnk/1.json", "echo x > %s/x/../sessions/1.json" % c,
                "dd if=/tmp/x of=%s/1.json" % s, "echo x | tee -a %s/1.json" % s,
                "python3 -c \"open('%s/1.json','w').write('{}')\"" % s, "python3 -I -c 'import os; os.environ[\"CLAUDE_CONFIG_DIR\"]'",
                "perl -e 'open(F, \">$ENV{CLAUDE_CONFIG_DIR}/sessions/1.json\")'",
                "ruby -e 'File.write(\"%s/1.json\", 1)'" % s, "node -e \"require('fs').writeFileSync('%s/1.json','{}')\"" % s,
                "bash -c 'echo x > %s/1.json'" % s, "echo $(echo x > %s/1.json)" % s]

        def check(expect):
            for cmd in cmds:
                self.assertEqual(self.bash(cmd, cwd=self.work), expect, cmd)
        self.both(check, "deny")

    def test_at_night_it_is_a_deny_all_the_same_and_never_an_ask(self):
        self.night(True)
        self.assertEqual(self.bash("echo x > %s/1.json" % self.s), "deny")
        self.night(False)
        self.assertEqual(self.bash("echo x > %s/1.json" % self.s), "deny")

    def test_reading_the_registry_and_writing_elsewhere_is_free(self):
        s, c = self.s, self.claude
        cmds = ["cat %s/100.json" % s, "ls %s" % s, "cp %s/100.json /tmp/o" % s, "grep boss %s/100.json > /tmp/o" % s,
                "cat %s/100.json | tee /tmp/o" % s, "cp -r %s /tmp/backup" % c, "jq . %s/100.json" % s,
                "echo x > %s/projects/m/memory.md" % c, "ls ~/.claude/sessions", "cat $CLAUDE_CONFIG_DIR/sessions/1.json",
                "python3 -c 'print(1)'", "echo x > /tmp/o 2>&1"]

        def check(expect):
            for cmd in cmds:
                self.assertEqual(self.bash(cmd, cwd=self.work), expect, cmd)
        self.both(check, None)

    def test_the_claude_folder_named_by_a_cd_or_a_variable_is_not_the_sessions_folder(self):
        c = self.claude
        for cmd in ["cd %s && cp x /tmp/y" % c, "cd %s && echo x >> projects/p/memory/a.md" % c,
                    "D=%s/projects; cp /tmp/a $D/a" % c, "cd %s && tee /tmp/o" % c,
                    "export C=%s; echo x > $C/settings.json" % c, "cd ~/.claude && cp x /tmp/y"]:
            def check(expect, cmd=cmd):
                self.assertEqual(self.bash(cmd, cwd=self.work), expect, cmd)
            self.both(check, None)

    def test_a_relative_target_that_resolves_into_the_sessions_folder_still_is_refused(self):
        c, s = self.claude, self.s
        for cmd in ["cd %s && echo x > sessions/1.json" % c, "cd %s && cp /tmp/x sessions/1.json" % c,
                    "cd %s && tee sessions/1.json" % c, "C=%s; echo x > $C/sessions/1.json" % c,
                    "C=%s; cp /tmp/x ${C}/sessions/1.json" % c, "cd %s/projects && echo x > ../sessions/1.json" % c,
                    "cd %s; rm 100.json" % s, "D=%s; cp /tmp/x $D" % s]:
            def check(expect, cmd=cmd):
                self.assertEqual(self.bash(cmd, cwd=self.work), expect, cmd)
            self.both(check, "deny")

    def test_the_file_tools_judge_the_path_as_written_and_the_real_one(self):
        paths = [os.path.join(self.s, "1.json"), os.path.join(self.work, "lnk", "1.json"),
                 os.path.join(self.claude, "x", "..", "sessions", "1.json"), os.path.join(self.s, "100.json")]

        def check(expect):
            for path in paths:
                for tool in ("Write", "Edit", "MultiEdit"):
                    self.assertEqual(self.files(tool, file_path=path, content="x"), expect, (tool, path))
            self.assertEqual(self.files("NotebookEdit", notebook_path=paths[0]), expect)
        self.both(check, "deny")
        self.assertIsNone(self.files("Read", file_path=paths[0]))
        self.assertIsNone(self.files("Write", file_path=os.path.join(self.claude, "settings.json"), content="x"))

    def test_the_session_name_the_door_trusts_cannot_be_forged_through_the_tools(self):
        """The forged file is what the attack would write; the guard stops the write, not the read."""
        forged = os.path.join(self.s, "999.json")
        self.assertEqual(self.bash("echo '%s' > %s" % (json.dumps({"pid": 999, "sessionId": "s-x",
                                                                    "name": "boss", "nameSource": "user"}),
                                                        forged)), "deny")
        self.assertFalse(os.path.exists(forged))
