import { describe, expect, it } from "vitest";
import {
  ConflictError,
  HttpError,
  NotFoundError,
  ValidationError,
} from "../src/errors/httpErrors.js";

describe("httpErrors", () => {
  it("sets status and code on typed errors", () => {
    expect(new ValidationError("bad").statusCode).toBe(400);
    expect(new NotFoundError().code).toBe("NOT_FOUND");
    expect(new ConflictError("dup").statusCode).toBe(409);
    expect(new HttpError(503, "down", "UNAVAILABLE").message).toBe("down");
  });
});
