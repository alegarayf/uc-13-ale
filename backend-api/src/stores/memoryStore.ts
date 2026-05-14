import type { DataStore } from "./DataStore.js";

/**
 * In-memory store for local development. Replace with richer models / sql.js as the app grows.
 */
export function createMemoryStore(): DataStore {
  return {
    label: "memory",
    async ping() {
      return { ok: true };
    },
  };
}
