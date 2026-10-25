---
name: push
description: Push a linked repository's main to its origin through the project's door, after the table's checks. Use only when the user types /push.
argument-hint: "<repo>"
disable-model-invocation: true
---

# /push

Push the main of `$ARGUMENTS` (a repository named in this project's table) through the door. This
is Claude Code only: the door rests on the plugin's guard, which Copilot does not have.

1. Check the argument is one repository name (letters, digits, dot, dash, underscore). If it is
   missing, run `python3 -I "${CLAUDE_PLUGIN_ROOT}/scripts/crew.py" config show` and ask which of
   the table's repositories.
2. Make sure what is to go is committed on main, then run exactly this line, alone, with nothing
   before or after it (no `cd`, no pipe, no redirect, no `&&`):

   ```
   python3 -I "${CLAUDE_PLUGIN_ROOT}/scripts/crew.py" push $ARGUMENTS
   ```

   The guard lets it through only from a session the table names among the repository's pushers,
   never from an agent. For a public repository it asks the user first; while a night is on it
   refuses.
3. The door pushes by fast-forward after its checks (origin, visibility, commit rules, the table's
   checks in a clean worktree) and prints what it did, or `refused:` and why. Report it as it is.
   When it refuses, say why and stop: do not try `git push`, another path to the script or a
   variation of the line; fix the cause (a message, a failing check, origin moved) and run it again
   only after that. Each run is in `releases.log` beside the project file.
