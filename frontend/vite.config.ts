import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The React app expects the service API at 8081. This proxy keeps the existing
// fetch calls working without changing the frontend contract.
const API_PATHS = ["/report", "/chat", "/approvals", "/metrics", "/standards",
  "/candidates", "/findings", "/coverage", "/health"];

export default defineConfig({
  base: "/app/",
  plugins: [react()],
  build: { outDir: "dist", emptyOutDir: true },
  server: {
    proxy: Object.fromEntries(
      API_PATHS.map((p) => [p, { target: "http://127.0.0.1:8081", changeOrigin: true }]),
    ),
  },
});
