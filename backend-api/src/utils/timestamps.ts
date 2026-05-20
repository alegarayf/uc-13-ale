import type { ApiTimestamp } from "../types/baseApiModel.js";

export function nowTimestamp(): ApiTimestamp {
  return new Date().toISOString();
}
