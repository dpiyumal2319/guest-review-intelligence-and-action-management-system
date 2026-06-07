## Web Workspace

This app is part of the repo root npm workspace.

Use the root-level commands:

```bash
npm ci
npm --workspace apps/web run dev
npm --workspace apps/web run lint
npm --workspace apps/web run build
```

Do not run `npm install` inside `apps/web`. A nested `apps/web/node_modules` can shadow the hoisted workspace dependencies, especially `next`, and cause broken builds.
