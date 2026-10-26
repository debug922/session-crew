"""Which words a command line writes to: redirections and the common writing verbs.

A cp or install writes its last operand (or the -t folder), mv and rm every operand, tee its
operands, sed or perl with -i their operands, dd its of=. A source that is only read is not a
target: `cp <home>/s/project.json /tmp/o` writes /tmp/o.
"""
import os
import re

SEPARATORS = set(";&|()")
EVERY_OPERAND = {"rm", "unlink", "rmdir", "mv", "touch", "truncate", "chmod", "chown", "tee", "shred"}
LAST_OPERAND = {"cp", "install", "rsync", "ln"}
WRAPPERS = {"env", "nice", "sudo", "time", "exec", "command", "nohup", "xargs", "export"}
REDIRECT = re.compile(r"([^>]*)>>?(.*)$")


def redirects(toks):
    """(plain words with the redirections taken out, the words redirected into)."""
    plain, targets, i = [], [], 0
    while i < len(toks):
        t = toks[i]
        if t.startswith("<"):  # an input redirection or a here document reads, it writes nothing
            i += 2 if t in ("<", "<<", "<<<") else 1
            continue
        m = REDIRECT.match(t) if ">" in t else None
        if not m:
            plain.append(t)
            i += 1
            continue
        pre, rest = m.groups()
        if pre and not pre.isdigit() and pre != "&":
            plain.append(pre)
        i += 1
        if not rest:
            if i < len(toks) and toks[i] == "|":  # >|
                i += 1
            rest = toks[i] if i < len(toks) else ""
            i += 1
        if rest and not rest.startswith("&") and rest != "/dev/null":
            targets.append(rest)
    return plain, targets


def segments(toks):
    seg = []
    for t in toks:
        if t and set(t) <= SEPARATORS:
            if seg:
                yield seg
            seg = []
        else:
            seg.append(t)
    if seg:
        yield seg


def _command(seg):
    """(program basename, its words after it) past env assignments and wrappers."""
    i = 0
    while i < len(seg) and ("=" in seg[i] and not seg[i].startswith("-")
                            or os.path.basename(seg[i]) in WRAPPERS):
        i += 1
    return (os.path.basename(seg[i]), seg[i + 1:]) if i < len(seg) else ("", [])


def segment_targets(verb, args):
    flags = [a for a in args if a.startswith("-")]
    operands = [a for a in args if not a.startswith("-")]
    if verb in ("cp", "install", "mv", "rsync", "ln"):
        for k, a in enumerate(args):
            if a in ("-t", "--target-directory") and k + 1 < len(args):
                return [args[k + 1]] + (operands if verb == "mv" else [])
            if a.startswith("--target-directory="):
                return [a.split("=", 1)[1]]
    if verb in EVERY_OPERAND:
        return operands
    if verb in LAST_OPERAND:
        return operands[-1:]
    if verb in ("sed", "perl") and any(re.fullmatch(r"-[A-Za-z]*i.*", f) for f in flags):
        return operands
    if verb == "dd":
        return [a[3:] for a in args if a.startswith("of=")]
    return []


def write_targets(toks):
    """[(verb, word)] for every word the line writes to; redirections have the verb ">"."""
    plain, redirected = redirects(toks)
    out = [(">", w) for w in redirected]
    for seg in segments(plain):
        verb, args = _command(seg)
        out += [(verb, w) for w in segment_targets(verb, args)]
    return out


def any_write(toks):
    """True when the line writes at all (a redirection or a writing verb), wherever."""
    plain, redirected = redirects(toks)
    return bool(redirected) or any(
        _command(seg)[0] in EVERY_OPERAND | LAST_OPERAND | {"sed", "perl", "dd"} and segment_targets(*_command(seg))
        for seg in segments(plain))


def moves_into(toks):
    """The words a line cds into, and the values it assigns to variables."""
    plain, _ = redirects(toks)
    cds = []
    for seg in segments(plain):
        verb, args = _command(seg)
        if verb in ("cd", "pushd"):
            cds += [a for a in args if not a.startswith("-")][:1]
    assigned = [t.partition("=")[2] for t in plain if re.match(r"\w+=", t)]
    return cds, assigned
