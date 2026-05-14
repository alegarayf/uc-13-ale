import path from "node:path";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const rootDir = path.resolve(__dirname, "..");
  const env = loadEnv(mode, rootDir, "");
  const port = Number(env.FRONTEND_PORT) || 5173;

  return {
    plugins: [react()],
    envDir: rootDir,
    server: { port, strictPort: true },
    preview: { port },
  };
});
