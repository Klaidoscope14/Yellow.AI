import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Served by the backend under /app in production; `base` makes built asset URLs
// resolve there. In dev, API calls are proxied to the backend on :8801.
const API_PATHS = ["/report", "/chat", "/approvals", "/metrics", "/standards",
  "/candidates", "/findings", "/coverage", "/health"];

export default defineConfig({
  base: "/app/",
  plugins: [react()],
  build: { outDir: "dist", emptyOutDir: true },
  server: {
    proxy: Object.fromEntries(
      API_PATHS.map((p) => [p, { target: "http://127.0.0.1:8801", changeOrigin: true }]),
    ),
  },
});
