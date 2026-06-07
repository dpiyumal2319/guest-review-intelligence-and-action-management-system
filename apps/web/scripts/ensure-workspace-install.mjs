import { existsSync, rmSync, lstatSync } from "node:fs";
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

// Next.js sometimes leaves a stale node_modules/next/dist build artifact
// in the workspace. This shadows the hoisted package and must be removed.
rmSync(nestedNextPath, { recursive: true, force: true });
