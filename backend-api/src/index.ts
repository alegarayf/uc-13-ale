import { createApp } from "./app.js";
import { getConfig } from "./config.js";

const cfg = getConfig();
const app = createApp();

app.listen(cfg.port, () => {
  console.log(`backend-api listening on http://localhost:${cfg.port} (DATA_STORE=${cfg.dataStore})`);
});
