import { TtlCache } from "../cache/TtlCache.js";
import type { Company } from "../types/company.js";
import type { CompaniesRepository } from "./companiesRepository.js";

function listKey(ownerEmail: string): string {
  return `companies:owner:${ownerEmail.trim().toLowerCase()}`;
}

function idKey(id: string): string {
  return `companies:id:${id}`;
}

export interface CachingCompaniesRepositoryOptions {
  ttlMs: number;
}

export function createCachingCompaniesRepository(
  inner: CompaniesRepository,
  options: CachingCompaniesRepositoryOptions,
): CompaniesRepository {
  const listCache = new TtlCache<Company[]>(options.ttlMs);
  const byIdCache = new TtlCache<Company>(options.ttlMs);

  return {
    async findByOwnerEmail(ownerEmail) {
      const key = listKey(ownerEmail);
      const cached = listCache.get(key);
      if (cached) return cached;

      const companies = await inner.findByOwnerEmail(ownerEmail);
      listCache.set(key, companies);
      for (const company of companies) {
        byIdCache.set(idKey(company.id), company);
      }
      return companies;
    },

    async findById(id) {
      const cached = byIdCache.get(idKey(id));
      if (cached) return cached;

      const company = await inner.findById(id);
      if (company) {
        byIdCache.set(idKey(id), company);
      }
      return company;
    },
  };
}
