import { describe, expect, it } from "vitest";
import { createMemoryCompaniesRepository } from "../src/repositories/companiesRepository.js";
import { DEFAULT_OPPORTUNITY_OWNER_EMAIL } from "../src/services/companiesService.js";

describe("createMemoryCompaniesRepository", () => {
  const repo = createMemoryCompaniesRepository();

  it("returns only companies for the given owner email", async () => {
    const companies = await repo.findByOwnerEmail(DEFAULT_OPPORTUNITY_OWNER_EMAIL);
    expect(companies.length).toBe(5);
    expect(
      companies.every(
        (c) =>
          c.opportunity_owner_email?.toLowerCase() ===
          DEFAULT_OPPORTUNITY_OWNER_EMAIL.toLowerCase(),
      ),
    ).toBe(true);
  });

  it("findById returns a company", async () => {
    const company = await repo.findById("opp-001");
    expect(company?.project_name).toBe("Northwind Expansion");
  });

  it("findById returns null for unknown id", async () => {
    expect(await repo.findById("missing")).toBeNull();
  });

  it("matches owner email case-insensitively", async () => {
    const companies = await repo.findByOwnerEmail("MCRysler@NimbleGravity.COM");
    expect(companies.length).toBe(5);
  });

  it("returns empty list for unknown owner", async () => {
    expect(await repo.findByOwnerEmail("nobody@example.com")).toEqual([]);
  });

  it("sorts results by project_name", async () => {
    const companies = await repo.findByOwnerEmail(DEFAULT_OPPORTUNITY_OWNER_EMAIL);
    const names = companies.map((c) => c.project_name);
    expect(names).toEqual([...names].sort((a, b) => a.localeCompare(b)));
  });
});
