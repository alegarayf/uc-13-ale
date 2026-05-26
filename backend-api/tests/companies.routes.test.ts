import { describe, expect, it } from "vitest";
import { createTestApp, testRequest } from "./helpers.js";
import { MEMORY_SEED_OWNER_COUNT } from "../src/repositories/companiesSeedData.js";
import { DEFAULT_OPPORTUNITY_OWNER_EMAIL } from "../src/services/companiesService.js";

describe("Companies API routes", () => {
  const app = createTestApp();
  const req = () => testRequest(app);

  describe("GET /api/companies", () => {
    it("returns companies for the default owner", async () => {
      const res = await req().get("/api/companies").expect(200);
      expect(res.body.data).toBeInstanceOf(Array);
      expect(res.body.data.length).toBe(MEMORY_SEED_OWNER_COUNT);
      expect(res.body.data[0]).toMatchObject({
        id: expect.any(String),
        project_name: expect.any(String),
        account_name: expect.any(String),
        opportunity_owner_email: DEFAULT_OPPORTUNITY_OWNER_EMAIL,
      });
    });
  });

  describe("GET /api/companies/:id", () => {
    it("returns a single company", async () => {
      const res = await req().get("/api/companies/opp-001").expect(200);
      expect(res.body.data.id).toBe("opp-001");
      expect(res.body.data.project_name).toBe("Northwind Expansion");
    });

    it("returns 404 for unknown id", async () => {
      const res = await req().get("/api/companies/missing").expect(404);
      expect(res.body.error.code).toBe("NOT_FOUND");
    });

    it("returns 404 for company owned by another user", async () => {
      const res = await req().get("/api/companies/opp-999").expect(404);
      expect(res.body.error.code).toBe("NOT_FOUND");
    });

    it("returns 400 when id is blank", async () => {
      const res = await req().get("/api/companies/%20").expect(400);
      expect(res.body.error.code).toBe("VALIDATION_ERROR");
      expect(res.body.error.message).toMatch(/id is required/i);
    });
  });
});
