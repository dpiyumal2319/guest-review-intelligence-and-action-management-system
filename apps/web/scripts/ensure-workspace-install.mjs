import { existsSync, lstatSync } from "node:fs";
import path from "node:path";
import process from "node:process";

const webRoot = process.cwd();
const nestedNextPath = path.join(webRoot, "node_modules", "next");

if (!existsSync(nestedNextPath)) {
  process.exit(0);
}

const stats = lstatSync(nestedNextPath);
if (stats.isSymbolicLink()) {
  process.exit(0);
}

console.error(
  [
    "Detected a nested apps/web/node_modules/next install.",
    "This shadows the workspace-hoisted Next.js package and breaks builds.",
    "Remove apps/web/node_modules and reinstall from the repo root with `npm ci`.",
  ].join("\n"),
);
process.exit(1);
