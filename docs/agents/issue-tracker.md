# Issue tracker: GitHub

Issues and PRDs for this repo live as GitHub issues. Use the `gh` CLI for all operations.

Repository: `dpiyumal2319/guest-review-intelligence-and-action-management-system`

Parent PRD: `#1`

Implementation issues: `#2` through `#17`

## Conventions

- Create an issue: `gh issue create --title "..." --body "..."`
- Read an issue: `gh issue view <number> --comments`
- If `gh issue view` fails because of GitHub's Projects classic GraphQL field, use `gh api repos/dpiyumal2319/guest-review-intelligence-and-action-management-system/issues/<number> --jq '.title, .body'`.
- List issues: `gh issue list --state open`
- Comment on an issue: `gh issue comment <number> --body "..."`
- Apply or remove labels: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- Close an issue: `gh issue close <number> --comment "..."`

Infer the repo from `git remote -v`; `gh` does this automatically when run inside a clone.

## When a skill says "publish to the issue tracker"

Create a GitHub issue.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --comments`.
