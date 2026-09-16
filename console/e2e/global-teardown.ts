import { existsSync, rmSync } from "node:fs";
import { dirname, basename, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const databasePath = resolve(repositoryRoot, ".e2e.sqlite3");

export default function globalTeardown() {
  if (basename(databasePath) !== ".e2e.sqlite3") {
    throw new Error(`Refusing to remove unexpected database: ${databasePath}`);
  }
  if (existsSync(databasePath)) {
    rmSync(databasePath);
  }
}
