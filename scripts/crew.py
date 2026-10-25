"""session-crew entry point: `python3 -I crew.py <command>` (stdlib only)."""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # -I drops it

import configcmd  # noqa: E402
import door  # noqa: E402
import handoff  # noqa: E402
import migrate  # noqa: E402
import recover  # noqa: E402
import registry  # noqa: E402
import rename  # noqa: E402
import size  # noqa: E402

HOOKS = {"size": size.hook, "rename": rename.hook, "start": migrate.hook_start}


def parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--name")
    common.add_argument("--session-id")
    common.add_argument("--cwd")
    p = argparse.ArgumentParser(prog="crew.py")
    sub = p.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("hook")
    h.add_argument("which", choices=sorted(HOOKS))
    ho = sub.add_parser("handoff", parents=[common])
    ho.add_argument("action", choices=["save", "status"])
    for cmd in ("migrate", "recover"):
        sub.add_parser(cmd, parents=[common]).add_argument("target", nargs="?")
    sub.add_parser("size", parents=[common]).add_argument("path", nargs="?")
    sub.add_parser("push", parents=[common]).add_argument("repo")
    tg = sub.add_parser("tag", parents=[common])
    tg.add_argument("repo")
    tg.add_argument("version")
    cf = sub.add_parser("config", parents=[common])
    cf.add_argument("action", choices=["show", "discover", "apply"])
    cf.add_argument("draft", nargs="?")
    return p


def run_hook(which):
    """A hook never holds up a message: any error goes to stderr, exit 1."""
    try:
        event = json.load(sys.stdin)
        return HOOKS[which](event if isinstance(event, dict) else {})
    except Exception as e:  # noqa: BLE001
        print("session-crew hook %s: %r" % (which, e), file=sys.stderr)
        return 1


def run_config(ident, args):
    if args.action == "apply":
        if not args.draft:
            print("config apply needs a draft (a file in the project's drafts folder)", file=sys.stderr)
            return 2
        return configcmd.apply(ident, args.draft)
    return configcmd.show(ident) if args.action == "show" else configcmd.discover(ident)


def main(argv):
    args = parser().parse_args(argv)
    if args.cmd == "hook":
        return run_hook(args.which)
    ident = registry.from_command_line(args.name, args.session_id, args.cwd)
    if args.cmd == "handoff":
        return handoff.run_save(ident) if args.action == "save" else handoff.run_status(ident)
    if args.cmd == "migrate":
        return migrate.run(ident, args.target)
    if args.cmd in ("push", "tag"):
        return door.run_command(ident, args.cmd, args.repo, getattr(args, "version", None))
    if args.cmd == "config":
        return run_config(ident, args)
    if args.cmd == "recover":
        return recover.run(ident, args.target or ident.name)
    return size.run_command(ident, args.path)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
