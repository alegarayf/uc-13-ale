import { beforeEach, describe, expect, it } from "vitest";
import { createTestApp, testRequest } from "./helpers.js";

describe("Rules API routes", () => {
  const app = createTestApp();
  const req = () => testRequest(app);

  beforeEach(() => {
    // Fresh app per file load; tests use seed data + create new rows with unique names.
  });

  describe("GET /api/rules", () => {
    it("returns seeded rules", async () => {
      const res = await req().get("/api/rules").expect(200);
      expect(res.body.data).toBeInstanceOf(Array);
      expect(res.body.data.length).toBeGreaterThanOrEqual(3);
      expect(res.body.data[0]).toMatchObject({
        id: expect.any(Number),
        name: expect.any(String),
        status: expect.stringMatching(/^(active|inactive)$/),
        created_at: expect.any(String),
        updated_at: expect.any(String),
      });
    });
  });

  describe("GET /api/rules/:id", () => {
    it("returns a single rule", async () => {
      const res = await req().get("/api/rules/1").expect(200);
      expect(res.body.data.id).toBe(1);
    });

    it("returns 404 for unknown id", async () => {
      const res = await req().get("/api/rules/99999").expect(404);
      expect(res.body.error.code).toBe("NOT_FOUND");
    });

    it("returns 400 for invalid id", async () => {
      const res = await req().get("/api/rules/not-a-number").expect(400);
      expect(res.body.error.code).toBe("VALIDATION_ERROR");
    });
  });

  describe("POST /api/rules", () => {
    it("creates a rule", async () => {
      const res = await req()
        .post("/api/rules")
        .send({
          name: "API test rule",
          description: "via supertest",
          comparison: ">=",
          minimum: 100,
          maximum: null,
          uom: "USD",
          status: "active",
          last_updated_by: "test-suite",
        })
        .expect(201);
      expect(res.body.data.id).toBeGreaterThan(3);
      expect(res.body.data.name).toBe("API test rule");
    });

    it("returns 400 when name missing", async () => {
      const res = await req().post("/api/rules").send({ comparison: "=" }).expect(400);
      expect(res.body.error.code).toBe("VALIDATION_ERROR");
    });

    it("returns 400 for invalid status", async () => {
      const res = await req()
        .post("/api/rules")
        .send({ name: "Bad status", status: "draft" })
        .expect(400);
      expect(res.body.error.code).toBe("VALIDATION_ERROR");
    });
  });

  describe("PUT /api/rules/:id", () => {
    it("replaces a rule", async () => {
      const res = await req()
        .put("/api/rules/2")
        .send({
          name: "Geography (updated)",
          description: "NA only",
          comparison: "=",
          minimum: null,
          maximum: null,
          uom: null,
          status: "active",
          last_updated_by: "test-suite",
        })
        .expect(200);
      expect(res.body.data.name).toBe("Geography (updated)");
      expect(res.body.data.created_at).toBeDefined();
    });

    it("allows null comparison on replace", async () => {
      await req()
        .put("/api/rules/1")
        .send({
          name: "Revenue",
          comparison: null,
          description: null,
          minimum: null,
          maximum: null,
          uom: null,
          status: "active",
        })
        .expect(200);
    });

    it("returns 404 when replacing unknown id", async () => {
      const res = await req()
        .put("/api/rules/99999")
        .send({
          name: "Missing",
          comparison: null,
          description: null,
          minimum: null,
          maximum: null,
          uom: null,
          status: "inactive",
        })
        .expect(404);
      expect(res.body.error.code).toBe("NOT_FOUND");
    });
  });

  describe("PATCH /api/rules/:id", () => {
    it("updates one field", async () => {
      const res = await req()
        .patch("/api/rules/3")
        .send({ minimum: 8 })
        .expect(200);
      expect(res.body.data.minimum).toBe(8);
    });

    it("returns 400 for empty body", async () => {
      await req().patch("/api/rules/1").send({}).expect(400);
    });

    it("updates status", async () => {
      const res = await req()
        .patch("/api/rules/3")
        .send({ status: "inactive" })
        .expect(200);
      expect(res.body.data.status).toBe("inactive");
    });
  });

  describe("DELETE /api/rules/:id", () => {
    it("deletes a created rule", async () => {
      const { body } = await req()
        .post("/api/rules")
        .send({ name: "To delete", comparison: "=" })
        .expect(201);
      await req().delete(`/api/rules/${body.data.id}`).expect(204);
      await req().get(`/api/rules/${body.data.id}`).expect(404);
    });

    it("returns 404 when deleting unknown id", async () => {
      const res = await req().delete("/api/rules/99999").expect(404);
      expect(res.body.error.code).toBe("NOT_FOUND");
    });
  });
});

describe("App health", () => {
  it("GET /health returns ok with memory store", async () => {
    const res = await testRequest(createTestApp()).get("/health").expect(200);
    expect(res.body.status).toBe("ok");
    expect(res.body.dataStore).toBe("memory");
  });
});
