import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

const webRoot = decodeURIComponent(new URL(".", import.meta.url).pathname).replace(
  /^\/([A-Za-z]:\/)/,
  "$1",
);

export default defineConfig({
  root: webRoot,
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          routing: ["react-router-dom", "@tanstack/react-query"],
          charts: ["recharts"],
          icons: ["lucide-react"],
        },
      },
    },
  },
  server: {
    port: 5173,
    allowedHosts: [".trycloudflare.com"],
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    exclude: ["e2e/**", "node_modules/**", "dist/**"],
    css: true,
    coverage: {
      provider: "v8",
      reporter: ["text", "html", "json-summary"],
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/main.tsx", "src/test/**", "src/**/*.test.{ts,tsx}"],
    },
  },
});
