import { describe, expect, it, vi } from "vitest";
import { Company } from "../src/types/company.js";
import { createCachingCompaniesRepository } from "../src/repositories/cachingCompaniesRepository.js";
import type { CompaniesRepository } from "../src/repositories/companiesRepository.js";

const ownerEmail = "owner@example.com";

const sample = new Company({
  id: "opp-1",
  project_name: "Cached Co",
  account_name: "Cached LLC",
  industry: "Tech",
  annual_revenue: null,
  employee_head_count: null,
  year_founded: null,
  ebitda: null,
  ebitda_margin: null,
  days_since_last_activity: null,
  website: null,
  source_scrub_url: null,
  linked_in_company_id: null,
  zoom_info_company_id: null,
  growth_rate_12_months: null,
  growth_rate_9_months: null,
  growth_rate_6_months: null,
  investors: null,
  name: null,
  description: null,
  stage_name: "Proposal",
  type: null,
  lead_source: "Web",
  opportunity_owner: null,
  opportunity_owner_role: null,
  status: "Open",
  opportunity_owner_email: ownerEmail,
});

function createMockInner(): CompaniesRepository {
  return {
    findByOwnerEmail: vi.fn(async () => [sample]),
    findById: vi.fn(async (id) => (id === "opp-1" ? sample : null)),
  };
}

describe("createCachingCompaniesRepository", () => {
  it("reuses cached list without second database call", async () => {
    const inner = createMockInner();
    const repo = createCachingCompaniesRepository(inner, { ttlMs: 60_000 });

    await repo.findByOwnerEmail(ownerEmail);
    await repo.findByOwnerEmail(ownerEmail);

    expect(inner.findByOwnerEmail).toHaveBeenCalledTimes(1);
  });

  it("normalizes owner email in cache key", async () => {
    const inner = createMockInner();
    const repo = createCachingCompaniesRepository(inner, { ttlMs: 60_000 });

    await repo.findByOwnerEmail("  Owner@Example.com  ");
    await repo.findByOwnerEmail("owner@example.com");

    expect(inner.findByOwnerEmail).toHaveBeenCalledTimes(1);
  });

  it("reuses cached findById", async () => {
    const inner = createMockInner();
    const repo = createCachingCompaniesRepository(inner, { ttlMs: 60_000 });

    await repo.findById("opp-1");
    await repo.findById("opp-1");

    expect(inner.findById).toHaveBeenCalledTimes(1);
  });

  it("does not cache null findById results", async () => {
    const inner = createMockInner();
    const repo = createCachingCompaniesRepository(inner, { ttlMs: 60_000 });

    await repo.findById("missing");
    await repo.findById("missing");

    expect(inner.findById).toHaveBeenCalledTimes(2);
  });

  it("warms per-id cache when listing by owner", async () => {
    const inner = createMockInner();
    const repo = createCachingCompaniesRepository(inner, { ttlMs: 60_000 });

    await repo.findByOwnerEmail(ownerEmail);
    await repo.findById("opp-1");

    expect(inner.findById).not.toHaveBeenCalled();
  });
});
