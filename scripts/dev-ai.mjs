import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "..");
const aiRoot = path.join(repoRoot, "backend-ai");
const port = process.env.BACKEND_AI_PORT || "8000";

const child = spawn(
  "python3",
  ["-m", "uvicorn", "app.main:app", "--reload", "--host", "0.0.0.0", "--port", port],
  {
    cwd: aiRoot,
    stdio: "inherit",
    env: process.env,
  },
);

child.on("exit", (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  process.exit(code ?? 1);
});
