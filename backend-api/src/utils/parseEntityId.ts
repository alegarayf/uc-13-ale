import { ValidationError } from "../errors/httpErrors.js";

export function parseEntityId(raw: string): number {
  const id = Number(raw);
  if (!Number.isInteger(id) || id <= 0) {
    throw new ValidationError("id must be a positive integer");
  }
  return id;
}
