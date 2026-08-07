---
name: start-phase
description: After a phase's pull request has merged, sync dev locally and cut a new phase-[#] branch from it, then push it to origin
---

## Purpose
Set up the local repo for the next phase of work right after the previous phase's pull request has merged into `dev`. This keeps every phase branch cut from an up-to-date `dev`, rather than from a stale local branch or from the just-merged phase branch.

## When to use
Right after the user tells you a pull request has been merged (typically phase branch into `dev`), and they are ready to start the next phase. The user will tell you which phase number to use when they invoke this skill.

## Inputs
- The phase number (e.g. `6`, `7`). If the user invokes the skill without one, ask for it before doing anything else.

## Steps

1. **Check for uncommitted work.** Run `git status` before switching branches. If there are uncommitted changes, stop and ask the user how to handle them (stash, commit, or discard) rather than assuming.

2. **Check out `dev` locally.**
   ```
   git checkout dev
   ```

3. **Fetch and sync with origin.**
   ```
   git fetch origin
   git pull origin dev
   ```
   This ensures the local `dev` has the just-merged pull request.

4. **Create the new phase branch from `dev`.**
   ```
   git checkout -b phase-[#] dev
   ```
   Use the exact phase number the user gave, formatted as `phase-6`, `phase-7`, etc.

5. **Publish the new branch to origin.**
   ```
   git push -u origin phase-[#]
   ```
   The `-u` sets the upstream tracking branch so future pushes on this branch don't need `origin phase-[#]` spelled out.

6. **Confirm.** Report the branch name created and pushed, and that it tracks origin.

## Notes
- Never force-push or delete branches as part of this skill.
- Do not merge, rebase, or touch the previous phase branch. It stays as-is after the PR merge; cleanup (deleting the merged branch) is a separate, explicit request if the user wants it.
- If `dev` doesn't exist locally yet, `git checkout dev` will fail. In that case use `git checkout -b dev origin/dev` instead.
