"""Reading a shell command line for the guard: its words, its git calls, what a push deletes."""
import os
import re
import shlex

GIT_OPTS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
GIT_OPTS_ALONE = {"--no-pager", "-P", "--paginate", "-p", "--bare", "--no-replace-objects",
                  "--literal-pathspecs", "--no-optional-locks"}
TAG_READ_FLAGS = {"-l", "--list", "-n", "--contains", "--no-contains", "--points-at", "--merged",
                  "--no-merged", "--sort", "--format", "-v", "--verify", "--column",
                  "--no-column", "-i", "--ignore-case"}
SHELLS = {"sh", "bash", "zsh", "dash"}
# A push's words that delete or rewrite on the remote; a short flag cluster counts when it holds
# f (--force) or d (--delete).
PUSH_DELETES = {"--force", "--delete", "--mirror", "--prune", "--force-if-includes"}
VERBS = re.compile(r"(?:^|[\s;&|(])(?:cp|mv|rm|tee|ln|install|chmod|touch|truncate|dd|rsync)\s"
                   r"|\bsed\s+-i|\bperl\s+-\w*i")
HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?\n\s*\2(?=\s|$)", re.DOTALL)
METHOD_DELETE = re.compile(r"(?:-X\s*=?\s*|--request[=\s]+|--method[=\s]+)['\"]?DELETE\b", re.IGNORECASE)


def tokens(cmd):
    """The command's words, heredoc bodies left out (they are text, not commands)."""
    body = HEREDOC.sub(lambda m: m.group(0).split("\n", 1)[0], cmd)
    try:
        lex = shlex.shlex(body, posix=True, punctuation_chars=";&|()")
        lex.whitespace_split = True
        return list(lex)
    except ValueError:
        return re.findall(r"[^\s;&|()'\"]+", body)


def without_messages(toks):
    """The words less a commit message given with -m: a message may name what it does not run."""
    skip = False
    for t in toks:
        if skip:
            skip = False
        elif t in ("-m", "--message"):
            skip = True
        elif not t.startswith("--message="):
            yield t


def _has_c(flag):
    """True for -c and for a short flag cluster holding c (-lc, -ec): the next word is a command."""
    return flag.startswith("-") and not flag.startswith("--") and "c" in flag[1:]


def git_calls(toks, depth=0):
    """Yields (subcommand, args, options before it) for every git call, nested shells included."""
    for i, tok in enumerate(toks):
        name = os.path.basename(tok)
        if name in SHELLS and i + 2 < len(toks) and depth < 3 and _has_c(toks[i + 1]):
            yield from git_calls(tokens(toks[i + 2]), depth + 1)
        elif name == "eval" and i + 1 < len(toks) and depth < 3:
            yield from git_calls(tokens(" ".join(toks[i + 1:])), depth + 1)
        elif name == "git":
            j = i + 1
            while j < len(toks):
                t = toks[j]
                if t in GIT_OPTS_WITH_VALUE:
                    j += 2
                elif t in GIT_OPTS_ALONE or any(t.startswith(o + "=") for o in GIT_OPTS_WITH_VALUE):
                    j += 1
                else:
                    break
            if j < len(toks):
                end = j + 1
                while end < len(toks) and not set(toks[end]) <= set(";&|()"):
                    end += 1
                yield toks[j], toks[j + 1:end], toks[i + 1:j]


def tag_writes(args):
    """True when a `git tag` creates or deletes (listing and reading flags are not this)."""
    if not args:
        return False
    first = args[0]
    return not (first in TAG_READ_FLAGS or first.startswith((
        "--sort=", "--format=", "--contains=", "--points-at=", "--merged=", "-n")))


def push_deletes(args):
    """True when a push's words delete or rewrite something on the remote."""
    for a in args:
        if a in PUSH_DELETES or a.startswith(("--force-with-lease", "--force-if-includes")):
            return True
        if re.fullmatch(r"-[A-Za-z]+", a) and set(a[1:]) & {"f", "d"}:
            return True
        if a.startswith(("+", ":")):
            return True
    return False


def github_deletes(cmd, toks):
    """True when the command deletes something on GitHub: a gh subcommand that deletes, or a DELETE
    to its API through gh api or curl."""
    for i, tok in enumerate(toks):
        base = os.path.basename(tok)
        if base == "gh" and (any("delete" in w for w in toks[i + 1:i + 4])
                             or toks[i + 1:i + 2] == ["api"] and METHOD_DELETE.search(cmd)):
            return True
        if base == "curl" and "github.com" in cmd and METHOD_DELETE.search(cmd):
            return True
    return False


def git_start_dir(opts, cwd):
    """Where a git call runs: cwd moved by every -C; None when --git-dir or --work-tree decides."""
    here = cwd
    it = iter(opts)
    for t in it:
        if t == "-C":
            here = os.path.join(here, os.path.expanduser(next(it, "")))
        elif t in ("--git-dir", "--work-tree") or t.startswith(("--git-dir=", "--work-tree=")):
            return None
    return here


def writes_to(named, patterns):
    """True when the words write to something matching one of the regular expressions: a writing
    verb beside it, or a redirection into it (reading it, or redirecting elsewhere, is not)."""
    if not any(re.search(p, named) for p in patterns):
        return False
    return bool(VERBS.search(named)) or any(
        re.search(r"(?:&\s*>|>>|>\s*\||>)\s*['\"]?\S*" + p, named) for p in patterns)


def _group(text, start):
    """The text inside the parentheses that open at text[start - 1], and where they close."""
    depth, i = 1, start
    while i < len(text) and depth:
        depth += {"(": 1, ")": -1}.get(text[i], 0)
        i += 1
    return text[start:i - 1], i


def nested_texts(cmd, depth=0):
    """Command lines inside a command line: the body of a heredoc that feeds a shell or eval, the
    contents of $( ) and of backticks, each also searched in turn. A heredoc feeding git commit or
    cat stays text."""
    out = []
    for m in HEREDOC.finditer(cmd):
        head = cmd[:m.start()].split("\n")[-1]
        words = tokens(re.split(r"[;&|(]", head)[-1])
        word = next((w for w in words if "=" not in w and w not in ("sudo", "env")), "")
        if os.path.basename(word) in SHELLS | {"eval"}:
            out.append(m.group(0).split("\n", 1)[1].rsplit("\n", 1)[0])
    i = cmd.find("$(")
    while i != -1:
        inner, end = _group(cmd, i + 2)
        out.append(inner)
        i = cmd.find("$(", end)
    out += re.findall(r"`([^`]*)`", cmd)
    if depth < 3:
        for text in list(out):
            out += nested_texts(text, depth + 1)
    return out
