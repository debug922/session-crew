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
            "python3 crew.py migrate",
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
                    "node -e \"require('fs').writeFileSync('%s', '{}')\"" % p]:
            self.assertEqual(self.bash(cmd), "ask", cmd)
        self.assertEqual(self.bash("python3 -c \"import shutil; shutil.copy('a', '%s/hooks/hooks.json')\""
                                   % guard.ROOT), "deny")
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


class OnlyWhatIsRun(GuardCase):
    """A crew.py that is only an argument is not a door: ordinary work on session-crew's own
    repository goes on from a configured folder."""

    def setUp(self):
        super().setUp()
        self.copy = os.path.join(self.work, "copy-of-the-repository")
        os.makedirs(os.path.join(self.copy, "scripts"))
        with open(os.path.join(self.copy, "scripts", "crew.py"), "w") as f:
            f.write("print('x')\n")
        self.git("copy-of-the-repository", "init", "-q", "-b", "main")

    def test_git_grep_and_the_like_may_name_a_crew_py(self):
        for cmd, cwd in [("git -C %s add scripts/crew.py" % self.copy, self.work),
                         ("git log -- scripts/crew.py", self.copy), ("git diff scripts/crew.py", self.copy),
                         ("grep -n x scripts/crew.py", self.copy), ("sed -n 1,5p scripts/crew.py", self.copy),
                         ("cat scripts/crew.py", self.copy), ("wc -l scripts/crew.py", self.copy),
                         ("vim scripts/crew.py", self.copy), ("git add scripts/crew.py", self.copy),
                         ("git mv scripts/crew.py scripts/crew2.py", self.copy)]:
            self.assertIsNone(self.bash(cmd, cwd=cwd), cmd)

    def test_running_a_crew_py_of_a_copy_is_refused_in_every_way_it_can_be_run(self):
        for cmd in ["python3 -I scripts/crew.py push core", "python3 scripts/crew.py migrate",
                    "python3.12 -B scripts/crew.py migrate", "./scripts/crew.py migrate",
                    "scripts/crew.py migrate", "X=1 python3 scripts/crew.py migrate",
                    "nice python3 scripts/crew.py migrate", "bash -c 'python3 scripts/crew.py migrate'",
                    "bash -lc \"python3 -I scripts/crew.py push core\"", "eval python3 scripts/crew.py migrate",
                    "echo $(python3 scripts/crew.py migrate)", "echo `scripts/crew.py migrate`",
                    "bash <<'EOF'\npython3 scripts/crew.py migrate\nEOF", "python3 -I scripts/cr*.py push core",
                    "python3 scripts/?rew.py migrate", "ls; python3 scripts/crew.py migrate",
                    "true && python3 scripts/crew.py migrate", "bash scripts/crew.py", "source scripts/crew.py"]:
            self.assertEqual(self.bash(cmd, cwd=self.copy), "deny", cmd)

    def test_python_that_runs_no_file_is_not_a_door(self):
        for cmd in ["python3 -c 'print(1)' scripts/crew.py", "python3 -m unittest scripts/crew.py",
                    "python3 -I -m pyflakes scripts/crew.py"]:
            self.assertIsNone(self.bash(cmd, cwd=self.copy), cmd)

    def test_copying_the_installed_plugins_script_out_is_refused(self):
        for cmd in ["cp %s/scripts/crew.py /tmp/x.py" % guard.ROOT, "cp %s /tmp/x.py" % guard.CREW,
                    "cd %s && cp scripts/crew.py /tmp/x.py" % guard.ROOT,
                    "mv %s/scripts/crew.py /tmp/x.py" % guard.ROOT, "cp -r %s /tmp/plugin" % guard.ROOT,
                    "cp %s/scripts/c*.py /tmp/" % guard.ROOT, "git -C %s checkout ." % guard.ROOT]:
            self.assertEqual(self.bash(cmd), "deny", cmd)
        project.write(guard.ROOT, {"repos": self.entries})  # a project at the plugin's own folder
        self.assertEqual(self.bash("cp scripts/crew.py /tmp/x.py", cwd=guard.ROOT), "deny")


class CrewHomeRefined(GuardCase):
    def setUp(self):
        super().setUp()
        self.home = config.home()
        self.slug = os.path.join(self.home, "-some-slug")

    def test_the_file_tools_ask_for_anything_under_the_crew_home_but_drafts_and_handovers(self):
        for path in [os.path.join(self.home, "stray.json"), os.path.join(self.slug, "releases.log"),
                     os.path.join(self.slug, "project.json.prev"), os.path.join(self.slug, "x", "y.json"),
                     os.path.join(self.slug, "boss", "notes.txt"), os.path.join(self.slug, "boss", "a", "h.md"),
                     os.path.join(self.slug, "project.json")]:
            self.assertEqual(self.files("Write", file_path=path, content="x"), "ask", path)
        for path in [os.path.join(self.slug, "drafts", "d.json"), os.path.join(self.slug, "drafts", "sub", "d.json"),
                     os.path.join(self.slug, "boss", "20261026T000000Z-aaaaaaaa.md")]:
            self.assertIsNone(self.files("Write", file_path=path, content="x"), path)

    def test_a_line_that_cds_into_the_home_or_assigns_it_asks_when_it_also_writes(self):
        for cmd in ["cd %s && echo x > project.json" % self.slug, "cd %s; tee project.json" % self.slug,
                    "pushd %s && cp /tmp/x ." % self.home, "D=%s; echo x > $D/-s/project.json" % self.home,
                    "export H=%s && cp /tmp/x $H/-s/project.json" % self.slug,
                    "cd %s && rm project.json" % self.slug]:
            self.assertEqual(self.bash(cmd), "ask", cmd)
        for cmd in ["cd %s && cat project.json" % self.slug, "D=%s; ls $D" % self.slug,
                    "cd %s && ls" % self.home]:
            self.assertIsNone(self.bash(cmd), cmd)

    def test_a_copy_or_a_tee_only_reads_when_the_home_is_its_source(self):
        p = os.path.join(self.slug, "project.json")
        for cmd in ["cp %s /tmp/o" % p, "cat %s | tee /tmp/o" % p, "cp -r %s /tmp/backup" % self.slug,
                    "rsync -a %s/ /tmp/backup/" % self.slug, "install %s /tmp/o" % p, "cat %s > /tmp/o" % p,
                    "tee /tmp/o < %s" % p]:
            self.assertIsNone(self.bash(cmd), cmd)
        for cmd in ["cp x %s" % p, "cp -t %s x" % self.slug, "install x %s" % p, "rsync x %s" % p,
                    "tee %s" % p, "cat x | tee -a %s" % p, "mv x %s" % p, "dd if=x of=%s" % p]:
            self.assertEqual(self.bash(cmd), "ask", cmd)


class NotTheInstalledOne(GuardCase):
    """Another crew.py (a working checkout, a copy) may run v1's shapes and config show|discover,
    never the door or config apply: those only from the installed path."""

    def setUp(self):
        super().setUp()
        self.other = os.path.join(self.work, "checkout", "scripts", "crew.py")

    def line(self, rest, path=None):
        return "python3 -I %s %s" % (path or self.other, rest)

    def test_v1_and_config_reads_run_from_any_crew_py(self):
        for rest in ["migrate", "migrate alpha --cwd /d", "recover", "size", "handoff status", "hook size",
                     "config show", "config discover --cwd /d", HANDOFF]:
            for path in (self.other, "scripts/crew.py", "./crew.py", "/tmp/copy/crew.py"):
                self.assertIsNone(self.bash(self.line(rest, path)), (rest, path))

    def test_the_door_and_apply_run_only_from_the_installed_path(self):
        for rest in ["push lib", "tag core v0.1.0", "config apply d.json", "config apply --cwd /d d.json"]:
            for path in (self.other, "scripts/crew.py", "/tmp/copy/crew.py"):
                self.assertEqual(self.bash(self.line(rest, path)), "deny", (rest, path))
        self.assertIsNone(self.bash(self.line("push lib", guard.CREW)))

    def test_a_script_not_called_crew_py_is_outside_the_shape_rule(self):
        for path in ("/tmp/copy/door.py", "/tmp/copy/crew.py.bak", "/tmp/x/main.py"):
            self.assertIsNone(self.bash(self.line("migrate", path)), path)

    def test_apply_takes_its_cwd_before_or_after_the_draft(self):
        for rest in ["config apply d.json --cwd /d", "config apply --cwd /d d.json", "config apply d.json"]:
            self.assertEqual(self.bash(self.line(rest, guard.CREW)), "ask", rest)
        for rest in ["config apply --cwd d.json", "config apply --cwd /d", "config apply a.json b.json",
                     "config apply --cwd /d d.json --cwd /e", "config apply d.json --name x"]:
            self.assertEqual(self.bash(self.line(rest, guard.CREW)), "deny", rest)
