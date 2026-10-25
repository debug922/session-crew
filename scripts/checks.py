"""The checks a push waits for (the table's `checks`), run in a clean worktree of HEAD."""
import os
import shutil
import subprocess
import tempfile

import repos
from gitrun import Refused, git


def run(cmd, cwd, env):
    out = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    if out.returncode != 0:
        tail = (out.stdout + out.stderr).strip().splitlines()[-30:]
        raise Refused("%s failed in %s:\n%s" % (" ".join(cmd), cwd, "\n".join(tail)))


def program(argv):
    """argv with govulncheck found where `go install` puts it when it is not on PATH."""
    if argv[0] == "govulncheck" and not shutil.which("govulncheck"):
        return [os.path.expanduser("~/go/bin/govulncheck")] + argv[1:]
    return argv


def due(repo_dir, item, since):
    """True when the check runs: it names no folder to watch, or that folder changed since."""
    return "when_changed" not in item or bool(
        git(repo_dir, "diff", "--name-only", "%s..HEAD" % since, "--", item["when_changed"]))


def run_item(item, base, repo_dir, nice, env):
    if item.get("in_repo"):
        watched = item.get("when_changed") or item.get("in") or "."
        if git(repo_dir, "status", "--porcelain", "--", watched):
            raise Refused("%s has uncommitted changes: its checks would not test what is pushed"
                          % watched)
    run(nice + program(item["run"]), os.path.join(base, item.get("in", ".")),
        dict(env, **item.get("env", {})))


def run_checks(name, repo_dir, entry, since, night):
    """Every check of the entry, those in a clean worktree first, then those in the repository
    itself (a folder like node_modules is not in the worktree). The limits follow the mode: no
    `nice` and the wider -p of a preset while a night is on."""
    items = repos.expand_checks(entry["checks"], night)
    nice = [] if night else ["nice", "-n", "10"]
    tree_items = [i for i in items if not i.get("in_repo") and due(repo_dir, i, since)]
    repo_items = [i for i in items if i.get("in_repo") and due(repo_dir, i, since)]
    if tree_items:
        work = tempfile.mkdtemp(prefix="crew-release-")
        tree = os.path.join(work, name)
        git(repo_dir, "worktree", "add", "--quiet", "--detach", tree, "HEAD")
        try:
            for item in tree_items:
                run_item(item, tree, repo_dir, nice, os.environ)
        finally:
            git(repo_dir, "worktree", "remove", "--force", tree, check=False)
            shutil.rmtree(work, ignore_errors=True)
    for item in repo_items:
        run_item(item, repo_dir, repo_dir, nice, os.environ)
