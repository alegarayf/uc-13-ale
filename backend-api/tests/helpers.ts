import type { Express } from "express";
import request from "supertest";
import { createApp } from "../src/app.js";
import { createMemoryCompaniesRepository } from "../src/repositories/companiesRepository.js";
import { createMemoryRulesRepository } from "../src/repositories/rulesRepository.js";
import { CompaniesService } from "../src/services/companiesService.js";
import { RulesService } from "../src/services/rulesService.js";
import { createMemoryStore } from "../src/stores/memoryStore.js";

/** Express app wired to in-memory store/repository (isolated from `.env` data mode). */
export function createTestApp(): Express {
  const rulesService = new RulesService(createMemoryRulesRepository());
  const companiesService = new CompaniesService(createMemoryCompaniesRepository());
  return createApp({
    rulesService,
    companiesService,
    store: createMemoryStore(),
    dataStore: "memory",
    aiBaseUrl: "http://test-ai",
  });
}

export function testRequest(app: Express) {
  return request(app);
}
