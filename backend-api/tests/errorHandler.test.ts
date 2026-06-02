import { describe, expect, it } from "vitest";
import express from "express";
import request from "supertest";
import { HttpError } from "../src/errors/httpErrors.js";
import { errorHandler } from "../src/middleware/errorHandler.js";

describe("errorHandler", () => {
  const app = express();
  app.get("/boom-http", () => {
    throw new HttpError(418, "teapot", "TEAPOT");
  });
  app.get("/boom-unknown", () => {
    throw new Error("unexpected");
  });
  app.use(errorHandler);

  it("formats HttpError", async () => {
    const res = await request(app).get("/boom-http").expect(418);
    expect(res.body.error).toEqual({ message: "teapot", code: "TEAPOT" });
  });

  it("masks unknown errors as 500", async () => {
    const res = await request(app).get("/boom-unknown").expect(500);
    expect(res.body.error.code).toBe("INTERNAL_ERROR");
  });
});
