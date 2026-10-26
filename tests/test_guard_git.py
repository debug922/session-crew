"""Where a push goes, git inside other commands, and aliases: a push the guard cannot place or
resolve is refused in a configured project."""
import os

from guardhelp import GuardCase

OTHER = None  # the repository outside the table, with its own origin


class Destinations(GuardCase):
    def push(self, cmd, repo="other"):
        return self.bash(cmd, cwd=os.path.join(self.work, repo))

    def test_a_push_to_the_repositorys_own_origin_outside_the_table_is_the_users(self):
        for cmd in ["git push", "git push origin main", "git push -u origin main",
                    "git push git@github.com:x/else.git main", "git push /tmp/x.git main",
                    "git push -o ci.skip origin main", "git push --repo=git@github.com:x/else.git"]:
            self.assertIsNone(self.push(cmd), cmd)
        self.assertIsNone(self.bash("git -C other push origin main"))

    def test_a_push_whose_url_is_a_table_repository_is_refused_whatever_the_folder(self):
        for cmd in ["git push git@github.com:o/lib.git main", "git push https://github.com/O/LIB main",
                    "git push ssh://git@github.com/o/core.git", "git push --repo=git@github.com:o/lib.git",
                    "git push --repo git@github.com:o/lib.git", "git push -u git@github.com:o/site main"]:
            self.assertEqual(self.push(cmd), "deny", cmd)

    def test_every_spelling_of_a_table_repository_is_refused_and_one_that_cannot_be_read_too(self):
        for url in ["ssh://git@github.com:22/o/lib.git", "ssh://git@ssh.github.com:443/o/lib.git",
                    "https://www.github.com/o/lib", "git://github.com/o/core.git", "git@github.com:/o/lib.git",
                    "https://github.com/o/lib/", "https://github.com/O/LIB.git?x=1", "https://github.com/o/lib#f",
                    "git@ssh.github.com:o/site.git"]:
            self.assertEqual(self.push("git push %s main" % url), "deny", url)
        for url in ["https://github.com/o", "git@github.com:", "https://github.com/o/lib/extra",
                    "https://github.com.evil/o/lib", "https://github.com/"]:
            self.assertEqual(self.push("git push %s main" % url), "deny", url)  # names GitHub, no repository
        self.git("other", "remote", "set-url", "origin", "ssh://git@ssh.github.com:443/o/lib.git")
        self.assertEqual(self.push("git push"), "deny")

    def test_a_github_repository_outside_the_table_and_a_local_path_are_allowed(self):
        for url in ["ssh://git@ssh.github.com:443/x/else.git", "https://www.github.com/x/else/", "git@github.com:/x/else.git",
                    "../core", "/tmp/x.git", "file:///tmp/x.git", "https://example.org/o/lib"]:
            self.assertIsNone(self.push("git push %s main" % url), url)

    def test_a_remote_whose_url_or_pushurl_is_a_table_repository_is_refused(self):
        self.git("other", "remote", "set-url", "origin", "git@github.com:o/lib.git")
        for cmd in ["git push", "git push origin main"]:
            self.assertEqual(self.push(cmd), "deny", cmd)
        self.git("other", "remote", "set-url", "origin", "git@github.com:x/other.git")
        self.assertIsNone(self.push("git push"))
        self.git("other", "remote", "set-url", "--push", "origin", "git@github.com:o/core.git")
        self.assertEqual(self.push("git push"), "deny")

    def test_with_no_remote_given_the_branchs_push_remote_decides(self):
        self.git("other", "remote", "add", "evil", "git@github.com:o/lib.git")
        self.git("other", "config", "branch.main.pushRemote", "evil")
        self.assertEqual(self.push("git push"), "deny")
        self.git("other", "config", "--unset", "branch.main.pushRemote")
        self.git("other", "config", "remote.pushDefault", "evil")
        self.assertEqual(self.push("git push"), "deny")
        self.git("other", "config", "--unset", "remote.pushDefault")
        self.git("other", "config", "branch.main.remote", "evil")
        self.assertEqual(self.push("git push"), "deny")

    def test_what_cannot_be_resolved_is_refused(self):
        for cmd in ["git push upstream main",
                    "git remote add up git@github.com:x/y.git && git push up main",
                    "git remote set-url origin git@github.com:o/lib.git && git push",
                    "git config remote.origin.url git@github.com:o/lib.git && git push",
                    "git -c remote.origin.url=git@github.com:o/lib.git push"]:
            self.assertEqual(self.push(cmd), "deny", cmd)

    def test_url_rewrites_are_applied_before_judging(self):
        self.git("other", "config", "url.git@github.com:o/lib.git.insteadOf", "git@github.com:x/other.git")
        self.assertEqual(self.push("git push"), "deny")
        self.git("other", "config", "--unset", "url.git@github.com:o/lib.git.insteadOf")
        self.git("other", "config", "url.https://github.com/.insteadOf", "git@github.com:")
        self.assertIsNone(self.push("git push"))  # a rewrite to somewhere that is not the table's
        self.git("other", "config", "url.git@github.com:o/core.git.pushInsteadOf", "git@github.com:x/other.git")
        self.assertEqual(self.push("git push"), "deny")  # pushInsteadOf wins for a push

    def test_an_env_prefix_or_a_git_dir_makes_a_push_unplaceable(self):
        for cmd in ["GIT_DIR=../core/.git git push", "GIT_WORK_TREE=../core git push",
                    "GIT_CONFIG_COUNT=1 git push", "env GIT_DIR=../core/.git git push",
                    "git --git-dir=../core/.git push", "git --work-tree=../core push",
                    "cd ../core && git push"]:
            self.assertEqual(self.push(cmd), "deny", cmd)

    def test_a_tag_outside_the_table_is_still_the_users_and_inside_it_is_not(self):
        self.assertIsNone(self.push("git tag v1"))
        self.assertEqual(self.push("git tag v1", "core"), "deny")
        self.assertEqual(self.push("GIT_DIR=../core/.git git tag v1"), "deny")


class NestedAndAliases(GuardCase):
    def run_in(self, cmd, repo="core"):
        return self.bash(cmd, cwd=os.path.join(self.work, repo))

    def test_a_shell_with_a_flag_cluster_holding_c_is_parsed(self):
        for cmd in ["bash -lc 'git push'", "sh -ec \"git push origin main\"", "zsh -c 'git tag v1'",
                    "bash -c 'git push'", "dash -xc 'git push'"]:
            self.assertEqual(self.run_in(cmd), "deny", cmd)
        self.assertIsNone(self.run_in("bash -lc 'git push'", "other"))
        self.assertIsNone(self.run_in("bash -c 'echo hi'"))

    def test_a_heredoc_that_feeds_a_shell_is_parsed_and_one_that_feeds_text_is_not(self):
        for cmd in ["bash <<'EOF'\ngit push\nEOF", "sh <<EOF\ngit tag v1\nEOF",
                    "eval <<'E'\ngit push\nE", "cd . && zsh <<'EOF'\necho a\ngit push\nEOF"]:
            self.assertEqual(self.run_in(cmd), "deny", cmd)
        for cmd in ["cat <<'EOF'\ngit push\nEOF", "git commit -F - <<'EOF'\nMention git push here\nEOF",
                    "git commit -q -m 'Say git push is refused'", "bash <<'EOF'\necho hi\nEOF"]:
            self.assertIsNone(self.run_in(cmd), cmd)

    def test_command_substitutions_and_backticks_are_parsed(self):
        for cmd in ["echo $(git push)", "echo `git push`", "echo \"$(git tag v1)\"",
                    "echo $(echo $(git push))", "x=`git push origin main`"]:
            self.assertEqual(self.run_in(cmd), "deny", cmd)
        self.assertIsNone(self.run_in("echo $(git status)"))
        self.assertIsNone(self.run_in("echo $(git push)", "other"))

    def test_defining_an_alias_that_hides_a_push_or_a_tag_is_refused(self):
        for cmd in ["git -c alias.p=push p", "git -c alias.x='!git push' x", "git config alias.p push",
                    "git config --global alias.ship '!git push'", "git config alias.t 'tag -a'"]:
            self.assertEqual(self.run_in(cmd, "other"), "deny", cmd)
        for cmd in ["git config alias.st status", "git -c core.pager=cat log", "git config user.name x"]:
            self.assertIsNone(self.run_in(cmd, "other"), cmd)

    def test_an_alias_is_treated_as_what_it_expands_to(self):
        self.git("core", "config", "alias.p", "push")
        self.git("core", "config", "alias.ship", "!git push origin")
        self.git("core", "config", "alias.ts", "tag")
        self.git("core", "config", "alias.st", "status -s")
        self.git("other", "config", "alias.pp", "push origin")
        for cmd in ["git p", "git p origin main", "git ship", "git ts v1", "git -C core p"]:
            self.assertEqual(self.bash(cmd, cwd=self.work + ("/core" if "-C" not in cmd else "")),
                             "deny", cmd)
        self.assertIsNone(self.run_in("git st"))
        self.assertIsNone(self.run_in("git pp", "other"))  # outside the table, to its own origin
        self.git("other", "config", "alias.pf", "push --force")
        self.assertEqual(self.run_in("git pf", "other"), "ask")

    def test_nothing_of_this_is_enforced_without_a_project_file(self):
        import config
        os.remove(config.project_file(self.work))
        for cmd in ["bash -lc 'git push'", "echo $(git push)", "git -c alias.p=push p",
                    "GIT_DIR=x git push"]:
            self.assertIsNone(self.run_in(cmd), cmd)


class Blind(GuardCase):
    """A push the guard cannot place is refused: a cd, popd, env -C and the like anywhere in the
    line (nested texts included) make it so, and so does a program the guard cannot read."""

    def run_in(self, cmd, repo="other"):
        return self.bash(cmd, cwd=os.path.join(self.work, repo))

    def test_a_cd_in_any_nested_text_makes_the_push_unplaceable(self):
        for cmd in ["bash -c 'cd ../core && git push'", "sh -lc \"pushd ../core; git push\"",
                    "zsh -c 'popd; git push'", "dash -ec 'cd ../core && git push'",
                    "su -c 'cd ../core && git push' someone", "eval 'cd ../core && git push'",
                    "eval 'cd ../core'; git push", "bash <<'EOF'\ncd ../core\nEOF\ngit push",
                    "echo $(cd ../core); git push", "echo `cd ../core`; git push",
                    "sh -c 'bash -c \"cd ../core && git push\"'", "popd; git push"]:
            self.assertEqual(self.run_in(cmd), "deny", cmd)
        self.assertIsNone(self.run_in("bash -c 'git push'"))
        self.assertIsNone(self.run_in("bash -c 'echo hi'; git push"))

    def test_an_alias_that_runs_a_shell_with_a_cd_is_blind_too(self):
        self.git("other", "config", "alias.go", "!cd ../core && git push")
        self.assertEqual(self.run_in("git go"), "deny")

    def test_env_chdir_find_exec_and_ssh_make_it_unplaceable(self):
        for cmd in ["env -C ../core git push", "env --chdir=../core git push", "env --chdir ../core git push",
                    "env -C../core git push", "find . -maxdepth 1 -exec git push {} \;",
                    "find .. -execdir git push \;", "ssh localhost 'cd /x && git push'", "ssh host \"git push\"",
                    "ssh -p 22 host 'git -C core push'"]:
            self.assertEqual(self.run_in(cmd), "deny", cmd)
        for cmd in ["env FOO=1 git status", "find . -name x", "find . -exec ls {} \;", "ssh host 'ls'",
                    "env -i git status"]:
            self.assertIsNone(self.run_in(cmd), cmd)

    def test_a_variable_or_a_substitution_as_the_program_word_beside_push_or_tag_is_refused(self):
        for cmd in ["$G push", "${G} push origin", "\"$G\" tag v1", "G=git; $G push", "$(which git) push",
                    "`which git` push origin main", "true && $GIT push", "$G -C ../core push"]:
            self.assertEqual(self.run_in(cmd), "deny", cmd)
        for cmd in ["$EDITOR file", "$G status", "echo $G push", "$G log"]:
            self.assertIsNone(self.run_in(cmd), cmd)

    def test_writing_an_alias_is_refused_unless_its_value_names_nothing_that_matters(self):
        for cmd in ["git config alias.x 'cd ..'", "git config alias.x '!ls'", "git config alias.x push",
                    "git config alias.x 'pushd ..'", "git config --global alias.x 'tag -d'",
                    "git config alias.x=push", "git -c alias.x=status x"]:
            self.assertEqual(self.run_in(cmd), "deny", cmd)
        for cmd in ["git config alias.st status", "git config alias.lg 'log --oneline'", "git config user.name x"]:
            self.assertIsNone(self.run_in(cmd), cmd)

    def test_editing_the_repositorys_config_file_by_a_write_verb_is_refused(self):
        for cmd in ["echo '[alias]' >> .git/config", "sed -i '' 's/a/b/' .git/config", "cp x ../core/.git/config",
                    "tee -a .git/config", "echo x >> ~/.gitconfig", "mv x ../core/.git/config",
                    "cd .git && echo x >> config"]:
            self.assertEqual(self.run_in(cmd), "deny", cmd)
        for cmd in ["cat .git/config", "grep url .git/config", "cp .git/config /tmp/o", "ls .git"]:
            self.assertIsNone(self.run_in(cmd), cmd)
