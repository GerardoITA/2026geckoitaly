# Repository Instructions

This repository is an Europa Universalis IV mod.

## General rules

- Preserve EU4 / Paradox script syntax and the repository's existing conventions.
- Make only minimal, targeted changes.
- Never mass-format files.
- Never modify unrelated code.
- Preserve comments unless the requested change makes them obsolete.
- Preserve localization keys and file encoding.
- Before inventing a trigger, effect, modifier, scope, scripted trigger, or scripted effect, search the repository for existing working examples.
- Be especially careful with ROOT, FROM, PREV, owner scope, province scope, and country scope.
- When modifying existing mechanics, inspect how the repository currently implements them before changing anything.

## Git safety rules

- NEVER create Git commits.
- NEVER push to any remote.
- NEVER run `git commit`.
- NEVER run `git push`.
- NEVER amend commits.
- NEVER merge, rebase, reset, cherry-pick, or switch branches unless explicitly requested.
- The user alone is allowed to commit and push changes.
- Always leave changes uncommitted for manual review.
- At the end of every work cycle, inspect:
  - `git status`
  - `git diff --check`
  - `git diff`
- Report every modified, created, or deleted file.
- Report relevant old -> new values.
- Stop after presenting the changes for review.
## Shared context workflow

- At the start of work, read this AGENTS.md, .ai/PROJECT.md and .ai/HANDOFF.md, plus any applicable nested instructions. Claude Code also reads CLAUDE.md; preserve its existing imports and instructions.
- Use PROJECT.md for persistent architecture, conventions and verified workflows. Keep session history and transient status out of it.
- Use HANDOFF.md for temporary operational status. Update it when explicitly asked to prepare a handoff; include verified changes, checks, blockers and next steps. This request initializes it.
- Preserve project-specific instructions and existing user changes. Do not infer that an old handoff authorizes new work.
- Never commit, amend or push. Do not reset, discard work, or perform destructive Git operations. Leave changes for user review.
- Keep changes minimal and documentation concise. Run checks relevant to the change and distinguish fresh results from historical reports.
