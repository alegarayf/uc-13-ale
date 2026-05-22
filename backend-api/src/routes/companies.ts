import { Router, type Request } from "express";
import { asyncHandler } from "../middleware/asyncHandler.js";
import type { CompaniesService } from "../services/companiesService.js";
import { ValidationError } from "../errors/httpErrors.js";

function routeId(req: Request): string {
  const id = req.params.id;
  const raw = Array.isArray(id) ? id[0]! : id!;
  const trimmed = raw?.trim();
  if (!trimmed) {
    throw new ValidationError("id is required");
  }
  return trimmed;
}

export function createCompaniesRouter(service: CompaniesService): Router {
  const router = Router();

  router.get(
    "/",
    asyncHandler(async (_req, res) => {
      const companies = await service.listForCurrentUser();
      res.json({ data: companies });
    }),
  );

  router.get(
    "/:id",
    asyncHandler(async (req, res) => {
      const company = await service.getById(routeId(req));
      res.json({ data: company });
    }),
  );

  return router;
}
