import { defineConfig, devices } from "@playwright/test";
import { resolve } from "node:path";

const repositoryRoot = resolve(import.meta.dirname, "..");
const localChromiumExecutable = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: "list",
  globalSetup: "./e2e/global-setup.ts",
  globalTeardown: "./e2e/global-teardown.ts",
  use: {
    baseURL: "http://127.0.0.1:8011",
    trace: "off",
    screenshot: "off",
  },
  webServer: {
    command: "npm run build && DJANGO_SETTINGS_MODULE=restock.e2e_settings ../.venv/bin/python ../manage.py runserver 127.0.0.1:8011 --noreload",
    cwd: resolve(repositoryRoot, "console"),
    url: "http://127.0.0.1:8011/healthz",
    timeout: 120_000,
    reuseExistingServer: false,
  },
  projects: [{
    name: "chromium",
    use: {
      ...devices["Desktop Chrome"],
      ...(localChromiumExecutable ? { launchOptions: { executablePath: localChromiumExecutable } } : {}),
    },
  }],
});
