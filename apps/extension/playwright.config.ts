import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  testMatch: "**/*.spec.ts",
  workers: 1,
  retries: 0,
  timeout: 60000,
  use: { trace: "retain-on-failure" },
  webServer: [
    {
      command:
        "../../.venv/bin/flask --app wsgi db upgrade && ../../.venv/bin/flask --app wsgi run --host 127.0.0.1 --port 5000",
      cwd: "../api",
      url: "http://127.0.0.1:5000/api/health/ready",
      reuseExistingServer: false,
    },
    {
      command: "npm run dev",
      cwd: "../web",
      url: "http://localhost:5173",
      reuseExistingServer: false,
    },
  ],
});
