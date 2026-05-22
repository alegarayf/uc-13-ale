import { describe, expect, it, vi } from "vitest";
import request from "supertest";
import { createApp } from "../src/app.js";

describe("createApp", () => {
  it("returns 500 when store ping fails", async () => {
    const app = createApp({
      store: {
        label: "broken",
        ping: vi.fn().mockRejectedValue(new Error("db down")),
      },
      dataStore: "memory",
    });
    const res = await request(app).get("/health").expect(500);
    expect(res.body.status).toBe("error");
  });

  it("exposes config endpoint", async () => {
    const app = createApp({ dataStore: "memory", aiBaseUrl: "http://ai" });
    const res = await request(app).get("/api/config").expect(200);
    expect(res.body).toMatchObject({ dataStore: "memory", aiBaseUrl: "http://ai" });
    expect(res.body.cache).toMatchObject({ enabled: expect.any(Boolean), ttlSeconds: expect.any(Number) });
  });

  it("mounts companies read API with default test app", async () => {
    const app = createApp({ dataStore: "memory" });
    const res = await request(app).get("/api/companies").expect(200);
    expect(res.body.data).toBeInstanceOf(Array);
    expect(res.body.data.length).toBeGreaterThan(0);
  });
});
