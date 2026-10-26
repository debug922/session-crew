"""What the guard keeps from a session's hands: Claude Code's registry of sessions (which the door
and the guard take as proof of a name) and session-crew's own home (which grants pushes)."""
import os
import re

import config
import writes
from verdict import Verdict

INLINE_REGISTRY = re.compile(r"\.claude/sessions|CLAUDE_CONFIG_DIR")
REMOVERS = {"mv", "rm", "ln", "rmdir", "unlink", "shred"}


def expand(word, cwd):
    """A word as a path, ~ and the known variables put in, .. resolved, no symlink followed."""
    home = os.path.expanduser("~")
    for var, value in (("HOME", home), ("CLAUDE_CONFIG_DIR", config.claude_dir()),
                       ("SESSION_CREW_HOME", config.home())):
        word = word.replace("${%s}" % var, value).replace("$" + var, value)
    word = os.path.expanduser(word)
    return os.path.normpath(word if os.path.isabs(word) else os.path.join(cwd, word))


def spellings(path):
    return {path, os.path.realpath(path)}


def under(path, folder):
    return path == folder or path.startswith(folder + os.sep)


def sessions_dirs():
    return {os.path.normpath(os.path.join(d, "sessions"))
            for d in (config.claude_dir(), os.path.realpath(config.claude_dir()))}


def claude_dirs():
    return {os.path.normpath(config.claude_dir()), os.path.realpath(config.claude_dir())}


def crew_homes():
    return {os.path.normpath(config.home()), os.path.realpath(config.home())}


def in_sessions(path):
    return any(under(p, d) for p in spellings(path) for d in sessions_dirs()) \
        or ".claude/sessions" in path + "/"


def in_crew_home(path):
    return any(under(p, h) for p in spellings(path) for h in crew_homes()) \
        or ".session-crew" in path.split(os.sep)


def hits(toks, cwd, direct, indirect):
    """True when the line writes to a path `direct` accepts, or cds into or assigns a path
    `indirect` accepts and writes at all (the written word may then be relative or a variable)."""
    for verb, word in writes.write_targets(toks):
        if direct(verb, expand(word, cwd)):
            return True
    cds, assigned = writes.moves_into(toks)
    return writes.any_write(toks) and any(indirect(expand(w, cwd)) for w in cds + [v for _, v in assigned])


def substitute(word, env):
    """The word with the variables the line itself assigned put in."""
    for name, value in env.items():
        word = word.replace("${%s}" % name, value).replace("$" + name, value)
    return word


def registry_hit(toks, cwd, code):
    """True for a write into Claude Code's sessions folder, a mv, rm or ln of that folder or of the
    config folder itself, a cd into the sessions folder or a variable naming it beside a write, a
    relative or variable target that resolves into it, or interpreter code naming it. Naming the
    config folder alone (`cd ~/.claude && cp x /tmp/y`) is not enough."""
    cds, assigned = writes.moves_into(toks)
    env = dict(assigned)
    here = expand(substitute(cds[-1], env), cwd) if cds else cwd
    for verb, word in writes.write_targets(toks):
        path = expand(substitute(word, env), here)
        if in_sessions(path) or (verb in REMOVERS and path in claude_dirs()):
            return True
    if writes.any_write(toks) and any(in_sessions(expand(w, cwd)) for w in cds + [v for _, v in assigned]):
        return True
    return any(INLINE_REGISTRY.search(c) or any(d in c for d in sessions_dirs()) for c in code)


def crew_home_hit(toks, cwd):
    return hits(toks, cwd, lambda verb, path: in_crew_home(path), in_crew_home)


def exempt_for_tools(path):
    """Under the crew home, what a file tool may still write: <slug>/drafts/ and the handoff
    folders <slug>/<name>/*.md."""
    for h in sorted(crew_homes(), key=len, reverse=True):
        if under(path, h):
            rel = os.path.relpath(path, h).split(os.sep)
            return (len(rel) >= 3 and rel[1] == "drafts") or (len(rel) == 3 and rel[2].endswith(".md"))
    return False


INTERPRETER = re.compile(r"(?:python[\d.]*|perl|ruby|node)")
INLINE_FLAG = re.compile(r"-[A-Za-z]*[ceE]")
APPLY_WORDS = re.compile(r"crew\.py[\"']?\s+config\s+apply\b")
CONFIG_ASK = ("This writes session-crew's configuration (the project file, which decides who pushes "
              "what, or the plugin's own folder). It runs only if the user confirms.")


def inline_code(toks):
    """The code strings given to an interpreter with -c or -e (python, perl, ruby, node)."""
    for i, t in enumerate(toks):
        if not INTERPRETER.fullmatch(os.path.basename(t)):
            continue
        for k in range(i + 1, len(toks)):
            if set(toks[k]) <= set(";&|()"):
                break
            if INLINE_FLAG.fullmatch(toks[k]) and k + 1 < len(toks):
                yield toks[k + 1]
                break


def registry_verdict(texts, cwd):
    """A deny for a write into Claude Code's registry, whatever the folder."""
    for toks in texts:
        if registry_hit(toks, cwd, list(inline_code(toks))):
            return Verdict("deny", "This writes into Claude Code's registry of sessions (or moves the "
                                   "folder). Only Claude Code writes those files, and the door and "
                                   "the guard take them as proof of who a session is: never from a "
                                   "tool. Reading them is free.")
    return None


def configuration(named, texts, cwd, plugin):
    """`config apply`, a write to the crew home or the plugin's folder, or interpreter code that
    names them: an ask."""
    if APPLY_WORDS.search(named):
        return Verdict("ask", "`config apply` writes the project file, which decides who pushes "
                              "what. It runs only if the user confirms.")
    for toks in texts:
        if crew_home_hit(toks, cwd) or hits(toks, cwd, lambda v, p: any(under(p, d) for d in plugin),
                                            lambda p: any(under(p, d) for d in plugin)):
            return Verdict("ask", CONFIG_ASK)
        mine = [r"\.session-crew", re.escape(config.home())] + [re.escape(d) for d in plugin]
        if any(re.search(m, c) for c in inline_code(toks) for m in mine):
            return Verdict("ask", CONFIG_ASK)
    return None


def git_config_edit(texts, cwd):
    """A deny for a write verb or redirection into a git configuration file (.git/config,
    .gitconfig): an alias or a url rewrite there would hide a push."""
    def direct(verb, path):
        base = os.path.basename(path)
        return base in (".gitconfig", "gitconfig") or (base == "config" and ".git" in path.split(os.sep))
    for toks in texts:
        if hits(toks, cwd, direct, lambda p: direct("", os.path.join(p, "config"))):
            return Verdict("deny", "This writes a git configuration file, where an alias or a url "
                                   "rewrite could hide a push. Use git config, and keep its value "
                                   "off push, tag and cd.")
    return None
