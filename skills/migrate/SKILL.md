---
name: migrate
description: Resume a session from its handoff in a fresh conversation, or recover it from the old transcript after a crash.
argument-hint: "[name]"
disable-model-invocation: true
---

# /migrate

Run the script and read what it prints:

```
python3 -I "${CLAUDE_PLUGIN_ROOT}/scripts/crew.py" migrate $ARGUMENTS
```

(Under Copilot add `--name NAME --cwd DIR`.) It prints the latest pending handoff for the name,
then this session's entry from the project configuration, and marks the handoff used. If a live
session already holds the name in this folder it says so first: pass that on to the maintainer.
With no pending handoff it recovers from the old transcript instead.

Then answer in at most ten lines: who this session is (its name and role), the item under way, and
the next step. Start from the handoff, not from the whole index of the memory: read a memory file
only when the handoff points to it.
