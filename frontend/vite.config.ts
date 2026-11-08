import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// In development the UI runs in a normal browser and talks to the Python
// backend through `python -m spni.devserver` (JSON-RPC + Server-Sent Events).
// In the packaged app the same build is loaded inside pywebview and calls
// window.pywebview.api directly.
const backend = process.env.SPNI_DEVSERVER ?? "http://127.0.0.1:8765";

export default defineConfig({
  base: "./",
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/rpc": backend,
      "/events": backend,
      "/media": backend,
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    chunkSizeWarningLimit: 1500,
  },
});
