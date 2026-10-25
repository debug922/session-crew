---
name: release
description: Push a linked repository's main and tag the release through the project's door. Use only when the user types /release.
argument-hint: "<repo> vX.Y.Z"
disable-model-invocation: true
---

# /release

Push the main of a repository and tag it `vX.Y.Z` through the door; `$ARGUMENTS` is the repository's
name and the version. Claude Code only, as `/push`.

1. Check the arguments are a repository name and a version of the form `vX.Y.Z`; ask for what is
   missing. The door accepts only the next patch or minor of the last tag with the same X (a new X,
   v1.0.0 included, is the user's), and only for a repository the table gives tags.
2. The version must be written in the commit being tagged, as the table says: `CHANGELOG.md` with a
   heading `## vX.Y.Z (date)` (name the Unreleased section and commit it first), or `VERSION` holding
   `X.Y.Z`. Do that and commit before the door, or it will refuse.
3. Run exactly this line, alone, with nothing before or after it (no `cd`, no pipe, no redirect):

   ```
   python3 -I "${CLAUDE_PLUGIN_ROOT}/scripts/crew.py" tag $ARGUMENTS
   ```

   The guard lets it through only from a session the table names among the repository's pushers,
   never from an agent; a public repository asks the user first, and a night refuses it.
4. The door runs the checks of `/push`, pushes main, makes the tag (lightweight or annotated, as the
   table says) and pushes it. Report what it printed. On `refused:` say why and stop; never use
   `git tag`, `git push` or `gh release create`.
