import { apiGet } from "./client.js";

export interface ApiConfig {
  dataStore: string;
  aiBaseUrl: string;
}

export async function fetchApiConfig(): Promise<ApiConfig> {
  return apiGet<ApiConfig>("/api/config");
}
