import { apiGet } from "./client.js";
import type { ApiItemResponse, ApiListResponse, Company } from "../types/company.js";

export async function fetchCompanies(): Promise<Company[]> {
  const res = await apiGet<ApiListResponse<Company>>("/api/companies");
  return res.data;
}

export async function fetchCompany(id: string): Promise<Company> {
  const res = await apiGet<ApiItemResponse<Company>>(`/api/companies/${encodeURIComponent(id)}`);
  return res.data;
}
