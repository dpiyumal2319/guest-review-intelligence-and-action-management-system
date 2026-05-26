---
name: github-issue-implementer
description: Implement a GitHub issue end to end from a local repository checkout. Use when the user gives a GitHub issue number or URL and asks to implement it, fix it, branch it, commit it, push it, or open a pull request that references the original issue.
---

# GitHub Issue Implementer

Implement one GitHub issue from a local checkout end to end.

## Workflow

1. Resolve the repository and issue.
   - Prefer the current git remote for the repo.
   - Fetch the issue title, body, labels, state, and comments with `gh issue view` or the GitHub connector.
   - If the issue is closed, ambiguous, or belongs to a different repository than the checkout, stop and ask for clarification.

2. Inspect the local checkout before branching.
   - Run `git status -sb`, `git branch --show-current`, and identify the default base branch.
   - If unrelated local changes exist, do not overwrite, revert, or stage them. Ask which changes belong in scope if the worktree is mixed.
   - If already on a task branch with relevant changes, continue there only when it clearly belongs to the issue; otherwise start fresh from the default branch.

3. Create a fresh branch from the base branch.
   - Fetch the remote base first: `git fetch origin <base>`.
   - Switch to the base and fast-forward when safe, or create from `origin/<base>` if the local base is dirty.
   - Use the repo branch prefix when configured; otherwise use `<implementer>/issue-<number>-<short-title>` where `<implementer>` is derived from the git user name (e.g. `git config user.name` shortened to a slug) or a prefix the user has stated.

4. Implement the issue.
   - Let the issue acceptance criteria drive the scope.
   - Read the project docs and existing patterns before editing.
   - Prefer maintained libraries, framework generators, and platform conventions when they are the industry-standard solution.
   - Keep changes focused on the issue; avoid unrelated refactors.

5. Validate.
   - Run the most relevant tests, builds, linters, type checks, or smoke checks available.
   - If a check cannot run because of an environment limitation, document the exact command and blocker.
   - Fix failures caused by the change before committing.

6. Commit and push.
   - Stage only files that belong to the issue.
   - Commit with a message that states what changed and why.
   - Push with upstream tracking: `git push -u origin <branch>`.

7. Open a pull request.
   - Target the original base branch unless the user requested another base.
   - Mention the original issue in the PR body with `Closes #<number>` when the PR should close it; otherwise use `Refs #<number>`.
   - Include a concise summary and validation list.
   - Open a draft PR by default unless the user explicitly asks for ready-for-review.
   - Prefer the GitHub connector for PR creation after the branch is pushed; use `gh pr create` as fallback.

## PR Body Template

```markdown
## Summary

- ...

Closes #<issue-number>

## Validation

- `...`
```

## Safety Rules

- Never use `git reset --hard`, `git checkout -- .`, or destructive cleanup unless the user explicitly requested it.
- Never stage unrelated user changes silently.
- Never close or edit the original issue unless the user asks.
- Do not invent acceptance criteria; if the issue is underspecified, ask or implement the smallest defensible vertical slice.
