import { describe, expect, it } from "vitest";
import express from "express";
import request from "supertest";
import { cacheControl } from "../src/middleware/cacheControl.js";

describe("cacheControl", () => {
  it("sets Cache-Control on GET JSON responses", async () => {
    const app = express();
    app.use(cacheControl(30));
    app.get("/items", (_req, res) => {
      res.json({ data: [] });
    });

    const res = await request(app).get("/items").expect(200);
    expect(res.headers["cache-control"]).toBe("private, max-age=30");
  });

  it("skips Cache-Control when max age is zero", async () => {
    const app = express();
    app.use(cacheControl(0));
    app.get("/items", (_req, res) => {
      res.json({ data: [] });
    });

    const res = await request(app).get("/items").expect(200);
    expect(res.headers["cache-control"]).toBeUndefined();
  });
});
