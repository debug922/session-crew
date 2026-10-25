"""A line naming the plugin's scripts must be exactly an allowed shape; writes anywhere in the crew
home ask; a line that reads is free."""
import os

from guardhelp import GuardCase

import config
import guard
import project

HANDOFF = "handoff save <<'HANDOFF'\n## Work under way\nx\nHANDOFF"


class Shapes(GuardCase):
    def crew(self, rest, path=None):
        return 'python3 -I "%s" %s' % (path or guard.CREW, rest)

    def test_the_door_and_the_configuration_and_v1s_own_forms_pass_as_the_skills_write_them(self):
        for rest in [HANDOFF, "handoff status", "handoff save --name n --cwd /d",
                     "handoff save --session-id s1 <<'H'\nbody\nH", "migrate", "migrate alpha",
                     "migrate --name alpha --cwd /d", "migrate alpha --cwd /d", "recover", "recover alpha",
                     "size", "size /tmp/t.jsonl", "hook size", "hook start", "hook rename",
                     "config show", "config discover", "config show --cwd /d", "push lib"]:
            self.assertIsNone(self.bash(self.crew(rest)), rest)
        self.assertIsNone(self.bash("python3 -I '%s' migrate" % guard.CREW))
        self.assertIsNone(self.bash("python3 -I %s migrate\n" % guard.CREW))

    def test_apply_asks(self):
        self.assertEqual(self.bash(self.crew("config apply d.json")), "ask")
        self.assertEqual(self.bash(self.crew("config apply d.json --cwd /d")), "ask")

    def test_any_other_shape_is_refused_and_the_refusal_names_the_allowed_ones(self):
        scripts = os.path.join(guard.ROOT, "scripts")
        bad = [
            "X=1 " + self.crew("migrate"), "GIT_DIR=x " + self.crew("push lib"),
            "bash -c '%s'" % self.crew("migrate"), "sh -lc '%s'" % self.crew("migrate"),
            "echo $(%s)" % self.crew("migrate"), "echo `%s`" % self.crew("migrate"),
            self.crew("migrate") + " && ls", self.crew("migrate") + " ; rm x", self.crew("migrate") + " | cat",
            self.crew("migrate") + " > /tmp/out", self.crew("size") + " 2>&1", "cd /tmp && " + self.crew("migrate"),
            "python3 -I scripts/crew.py migrate", "python3 -I ./crew.py migrate",
            "python3 -I /tmp/copy/crew.py migrate", "python3 crew.py migrate",
            "python3 -I %s/door.py" % scripts, "python3 -I %s/shapes.py" % scripts,
            "python3 -I %s/cr*.py migrate" % scripts, "python3 -I %s/s*/c?ew.py migrate" % scripts,
            "python3 -I %s/scripts/[c]rew.py migrate" % guard.ROOT, "python3 -I %s/*/crew.py" % guard.ROOT,
            "python3 -c 'import sys; sys.path.insert(0, \"%s\"); import door'" % scripts,
            self.crew("hook nonsense"), self.crew("push lib --cwd /d"), self.crew("push"),
            self.crew("tag lib v1"), self.crew("tag lib v0.1.0 extra"), self.crew("push ../lib"),
            self.crew("config apply d.json --name x"), self.crew("config apply"),
            self.crew("config discover --session-id s1"), self.crew("handoff save extra"),
            self.crew("migrate a b"), self.crew("migrate $HOME"), self.crew("migrate $(id)"),
            self.crew("migrate 'a b'"), self.crew("migrate a;b"), self.crew("migrate #x"),
            self.crew("handoff status <<'H'\nx\nH"),
            # a heredoc whose delimiter appears early, with commands after it
            "python3 -I \"%s\" handoff save <<'H'\nx\nH\nrm -rf y\nH" % guard.CREW,
            # an unquoted delimiter expands $(...) in its body
            "python3 -I \"%s\" handoff save <<H\n$(id)\nH" % guard.CREW,
            "python3 -I \"%s\" handoff save <<'H'\nx" % guard.CREW,
        ]
        for cmd in bad:
            self.assertEqual(self.bash(cmd), "deny", cmd)
        out = self.call(guard.run_bash, __import__("json").dumps({
            "tool_name": "Bash", "tool_input": {"command": "X=1 " + self.crew("migrate")},
            "cwd": self.work, "session_id": "s-boss"}))[1]
        self.assertIn("The allowed shapes", out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_a_refused_door_line_is_refused_from_a_relative_cwd_too(self):
        here = os.path.join(guard.ROOT, "scripts")
        project.write(here, {"repos": self.entries})
        self.assertEqual(self.bash("python3 -I crew.py push lib", cwd=here), "deny")
        self.assertEqual(self.bash("python3 -I ./cr*.py push lib", cwd=here), "deny")
        self.assertEqual(self.bash("rm ./*.py", cwd=here), "deny")

    def test_a_plain_read_of_the_scripts_is_free_but_writing_them_is_not(self):
        scripts = os.path.join(guard.ROOT, "scripts")
        for cmd in ["cat %s/crew.py" % scripts, "ls %s" % scripts, "grep -n push %s/door.py" % scripts,
                    "rg 'crew.py push' %s" % guard.ROOT, "head -20 %s/*.py" % scripts,
                    "ls %s 2>/dev/null" % scripts, "wc -l %s/guard.py" % scripts]:
            self.assertIsNone(self.bash(cmd), cmd)
        for cmd in ["cat %s/crew.py | python3" % scripts, "cat %s/crew.py; rm x" % scripts,
                    "cat $(ls %s)" % scripts]:
            self.assertEqual(self.bash(cmd), "deny", cmd)
        self.assertEqual(self.bash("cat x > %s/guard.py" % scripts), "ask")  # reads, but writes too

    def test_a_commit_message_that_names_the_script_is_still_text(self):
        for cmd in ['git commit -q -m "Fix crew.py push for lib"',
                    "git commit -F - <<'EOF'\nCall crew.py push lib\nEOF"]:
            self.assertIsNone(self.bash(cmd, cwd=self.work + "/other"), cmd)

    def test_nothing_is_enforced_in_a_folder_with_no_project_file_but_apply_still_asks(self):
        os.remove(config.project_file(self.work))
        for cmd in ["X=1 " + self.crew("migrate"), "bash -c '%s'" % self.crew("migrate"),
                    "python3 -I /tmp/copy/crew.py migrate"]:
            self.assertIsNone(self.bash(cmd), cmd)
        for cmd in ["X=1 " + self.crew("config apply d.json"), self.crew("config apply d.json"),
                    "python3 -I /tmp/copy/crew.py config apply d.json"]:
            self.assertEqual(self.bash(cmd), "ask", cmd)

    def test_at_night_apply_is_refused_and_the_door_line_of_a_private_repository_goes_on(self):
        self.night(True)
        self.assertEqual(self.bash(self.crew("config apply d.json")), "deny")
        self.assertIsNone(self.bash(self.crew("push lib")))
        self.assertEqual(self.bash("X=1 " + self.crew("push lib")), "deny")


class CrewHome(GuardCase):
    def setUp(self):
        super().setUp()
        self.slug = os.path.join(config.home(), "-some-slug")

    def test_a_write_to_any_level_of_the_crew_home_asks(self):
        for cmd in ["echo x > %s/drafts/d.json" % self.slug, "echo x >> %s/boss/h.md" % self.slug,
                    "echo x >| %s/project.json" % self.slug, "echo x &> %s/k" % self.slug,
                    "echo x > ~/.session-crew/-x/drafts/d.json", "ln -s /tmp/x %s/project.json" % self.slug,
                    "ln -s /tmp/x %s" % self.slug, "mv /tmp/x %s/boss" % self.slug, "rm -r %s" % self.slug,
                    "mv %s /tmp/gone" % self.slug, "cp /tmp/x %s/project.json" % self.slug,
                    "rm -rf ~/.session-crew", "tee %s/project.json" % self.slug,
                    "sed -i '' s/a/b/ ~/.session-crew/-x/project.json"]:
            self.assertEqual(self.bash(cmd), "ask", cmd)

    def test_reading_the_crew_home_is_free(self):
        for cmd in ["cat %s/project.json" % self.slug, "ls %s" % config.home(), "ls ~/.session-crew/-x",
                    "grep -rn lib %s" % self.slug, "jq . %s/project.json >/dev/null" % self.slug,
                    "head %s/boss/h.md 2>&1" % self.slug]:
            self.assertIsNone(self.bash(cmd), cmd)

    def test_inline_code_that_names_the_crew_home_or_the_plugin_asks(self):
        p = "%s/project.json" % self.slug
        for cmd in ["python3 -c \"open('%s','w').write('{}')\"" % p, "python3 -I -c \"import os; os.remove('%s')\"" % p,
                    "python -c \"open('~/.session-crew/x/project.json','w')\"",
                    "perl -e 'open(F, \">%s\")'" % p, "ruby -e 'File.write(\"%s\", 1)'" % p,
                    "node -e \"require('fs').writeFileSync('%s', '{}')\"" % p,
                    "python3 -c \"import shutil; shutil.copy('a', '%s/hooks/hooks.json')\"" % guard.ROOT]:
            self.assertEqual(self.bash(cmd), "ask", cmd)
        for cmd in ["python3 -c 'print(1)'", "python3 -m unittest", "node script.js", "perl -e 'print 1'",
                    "python3 -I -c 'import json'"]:
            self.assertIsNone(self.bash(cmd), cmd)

    def test_at_night_they_are_refused(self):
        self.night(True)
        self.assertEqual(self.bash("echo x > %s/drafts/d.json" % self.slug), "deny")
        self.assertEqual(self.bash("python3 -c \"open('%s/project.json')\"" % self.slug), "deny")

    def test_the_file_tools_judge_the_path_as_written_and_the_real_one(self):
        os.makedirs(self.slug)
        outside = os.path.join(self.tmp, "outside")
        os.makedirs(outside)
        link_dir = os.path.join(config.home(), "-linked")
        os.symlink(outside, link_dir)  # a folder in the home that points out of it
        into = os.path.join(self.tmp, "into.json")
        os.symlink(os.path.join(self.slug, "project.json"), into)  # a file outside pointing in
        for path in [os.path.join(link_dir, "project.json"),
                     os.path.join(self.work, "..", "crew", "-some-slug", "project.json"),
                     os.path.join(self.slug, "sub", "..", "project.json"), into,
                     os.path.join(self.slug, "deeper", "project.json")]:
            for tool in ("Write", "Edit"):
                self.assertEqual(self.files(tool, file_path=path, content="x"), "ask", (tool, path))
        self.assertIsNone(self.files("Write", file_path=os.path.join(self.slug, "drafts", "d.json"), content="x"))
        self.assertIsNone(self.files("Write", file_path=os.path.join(outside, "other.json"), content="x"))
