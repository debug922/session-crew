"""Running git for the door: one failure type, one way to ask."""
import subprocess


class Refused(Exception):
    """The door will not do this; the message says why."""


def git(repo_dir, *args, check=True):
    out = subprocess.run(["git", "-C", repo_dir, *args], capture_output=True, text=True)
    if check and out.returncode != 0:
        raise Refused("git %s: %s" % (" ".join(args), (out.stderr or out.stdout).strip()))
    return out.stdout.strip()


def is_ancestor(repo_dir, older, newer):
    return subprocess.run(["git", "-C", repo_dir, "merge-base", "--is-ancestor", older, newer],
                          capture_output=True).returncode == 0
