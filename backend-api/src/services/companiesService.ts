import { NotFoundError } from "../errors/httpErrors.js";
import type { CompaniesRepository } from "../repositories/companiesRepository.js";
import type { Company } from "../types/company.js";

/** Until auth is wired, opportunities are scoped to this owner email. */
export const DEFAULT_OPPORTUNITY_OWNER_EMAIL = "mcrysler@nimblegravity.com";

export class CompaniesService {
  constructor(private readonly repo: CompaniesRepository) {}

  async listForCurrentUser(): Promise<Company[]> {
    return this.repo.findByOwnerEmail(DEFAULT_OPPORTUNITY_OWNER_EMAIL);
  }

  async getById(id: string): Promise<Company> {
    const company = await this.repo.findById(id);
    if (!company) throw new NotFoundError(`Company not found: ${id}`);
    if (
      (company.opportunity_owner_email ?? "").trim().toLowerCase() !==
      DEFAULT_OPPORTUNITY_OWNER_EMAIL.toLowerCase()
    ) {
      throw new NotFoundError(`Company not found: ${id}`);
    }
    return company;
  }
}
