import { existsSync, rmSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const databasePath = resolve(repositoryRoot, ".e2e.sqlite3");
const python = resolve(repositoryRoot, ".venv/bin/python");

function runDjango(args: string[]) {
  const result = spawnSync(python, ["manage.py", ...args], {
    cwd: repositoryRoot,
    env: { ...process.env, DJANGO_SETTINGS_MODULE: "restock.e2e_settings" },
    stdio: "inherit",
  });
  if (result.status !== 0) {
    throw new Error(`Django command failed: ${args.join(" ")}`);
  }
}

export default function globalSetup() {
  if (existsSync(databasePath)) {
    if (databasePath.split("/").pop() !== ".e2e.sqlite3") {
      throw new Error(`Refusing to remove unexpected database: ${databasePath}`);
    }
    rmSync(databasePath);
  }
  runDjango(["migrate", "--noinput"]);
  runDjango(["seed_e2e"]);
}
