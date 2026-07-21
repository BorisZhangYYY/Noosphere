import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { cpSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [
    react(),
    {
      name: "bundle-vditor-runtime",
      closeBundle() {
        const target = resolve(frontendRoot, "dist/vditor/dist");
        mkdirSync(target, { recursive: true });
        cpSync(resolve(frontendRoot, "node_modules/vditor/dist"), target, { recursive: true });
      }
    }
  ],
  base: "/app/",
  build: {
    chunkSizeWarningLimit: 600,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("/node_modules/i18next/") || id.includes("/node_modules/react-i18next/")) {
            return "i18n-vendor";
          }
        }
      }
    }
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8080",
      "/health": "http://127.0.0.1:8080"
    }
  }
});
