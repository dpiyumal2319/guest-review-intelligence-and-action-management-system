# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Before exploring, read these

- `CONTEXT.md` at the repo root, if it exists.
- `CONTEXT-MAP.md` at the repo root, if it exists.
- `docs/adr/`, if ADRs exist.

If any of these files do not exist, proceed silently. The project currently uses a single-context layout.

## Use the glossary's vocabulary

When output names a domain concept, use the term as defined in `CONTEXT.md` if one exists. If the term is missing, note the gap rather than inventing conflicting language.

## Flag ADR conflicts

If output contradicts an existing ADR, surface it explicitly rather than silently overriding the decision.
