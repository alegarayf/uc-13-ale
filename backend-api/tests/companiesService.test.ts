import { beforeEach, describe, expect, it, vi } from "vitest";
import { NotFoundError } from "../src/errors/httpErrors.js";
import type { CompaniesRepository } from "../src/repositories/companiesRepository.js";
import {
  CompaniesService,
  DEFAULT_OPPORTUNITY_OWNER_EMAIL,
} from "../src/services/companiesService.js";
import { Company } from "../src/types/company.js";

const owned = new Company({
  id: "opp-001",
  project_name: "Northwind Expansion",
  account_name: "Northwind Traders",
  industry: "Manufacturing",
  annual_revenue: null,
  employee_head_count: null,
  year_founded: null,
  ebitda: null,
  ebitda_margin: null,
  days_since_last_activity: null,
  website: "https://northwind.example.com",
  source_scrub_url: null,
  linked_in_company_id: null,
  zoom_info_company_id: null,
  growth_rate_12_months: null,
  growth_rate_9_months: null,
  growth_rate_6_months: null,
  investors: null,
  name: null,
  description: null,
  stage_name: "Qualification",
  type: null,
  lead_source: "Partner Referral",
  opportunity_owner: null,
  opportunity_owner_role: null,
  status: "Open",
  opportunity_owner_email: DEFAULT_OPPORTUNITY_OWNER_EMAIL,
});

const otherOwner = new Company({
  ...owned,
  id: "opp-999",
  project_name: "Other",
  opportunity_owner_email: "other@example.com",
});

function createMockRepo(overrides: Partial<CompaniesRepository> = {}): CompaniesRepository {
  return {
    findByOwnerEmail: vi.fn(async () => [owned]),
    findById: vi.fn(async (id) => {
      if (id === "opp-001") return owned;
      if (id === "opp-999") return otherOwner;
      if (id === "no-owner") {
        return new Company({ ...owned, id: "no-owner", opportunity_owner_email: null });
      }
      return null;
    }),
    ...overrides,
  };
}

describe("CompaniesService", () => {
  let repo: CompaniesRepository;
  let service: CompaniesService;

  beforeEach(() => {
    repo = createMockRepo();
    service = new CompaniesService(repo);
  });

  it("lists companies for the default owner email", async () => {
    const companies = await service.listForCurrentUser();
    expect(companies).toEqual([owned]);
    expect(repo.findByOwnerEmail).toHaveBeenCalledWith(DEFAULT_OPPORTUNITY_OWNER_EMAIL);
  });

  it("returns a company by id when owned by the default user", async () => {
    const company = await service.getById("opp-001");
    expect(company.id).toBe("opp-001");
    expect(repo.findById).toHaveBeenCalledWith("opp-001");
  });

  it("throws NotFoundError when id does not exist", async () => {
    await expect(service.getById("missing")).rejects.toThrow(NotFoundError);
    await expect(service.getById("missing")).rejects.toThrow(/Company not found: missing/);
  });

  it("throws NotFoundError when company belongs to another owner", async () => {
    await expect(service.getById("opp-999")).rejects.toThrow(NotFoundError);
  });

  it("throws NotFoundError when opportunity_owner_email is null", async () => {
    await expect(service.getById("no-owner")).rejects.toThrow(NotFoundError);
  });
});
