import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { cpSync, createReadStream, existsSync, mkdirSync, statSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = dirname(fileURLToPath(import.meta.url));
const backendUrl = process.env.VITE_BACKEND_URL || "http://127.0.0.1:8080";
const vditorDist = resolve(frontendRoot, "node_modules/vditor/dist");
const vditorContentTypes: Record<string, string> = {
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".woff2": "font/woff2"
};

export default defineConfig({
  plugins: [
    react(),
    {
      name: "bundle-vditor-runtime",
      configureServer(server) {
        server.middlewares.use("/app/vditor/dist", (request, response, next) => {
          const pathname = decodeURIComponent((request.url ?? "/").split("?")[0]);
          const filePath = resolve(vditorDist, `.${pathname}`);
          if (!filePath.startsWith(`${vditorDist}/`) || !existsSync(filePath) || !statSync(filePath).isFile()) {
            next();
            return;
          }
          const extension = filePath.slice(filePath.lastIndexOf("."));
          response.setHeader("Content-Type", vditorContentTypes[extension] ?? "application/octet-stream");
          createReadStream(filePath).pipe(response);
        });
      },
      closeBundle() {
        const target = resolve(frontendRoot, "dist/vditor/dist");
        mkdirSync(target, { recursive: true });
        cpSync(vditorDist, target, { recursive: true });
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
      "/api": backendUrl,
      "/health": backendUrl
    }
  }
});
