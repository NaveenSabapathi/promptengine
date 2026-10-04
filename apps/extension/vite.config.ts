import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath, URL } from "node:url";
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    outDir: "dist/ui",
    emptyOutDir: true,
    rollupOptions: {
      input: { popup: fileURLToPath(new URL("./popup.html", import.meta.url)) },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test-setup.ts",
    restoreMocks: true,
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
