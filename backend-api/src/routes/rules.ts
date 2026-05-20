import { Router, type Request } from "express";
import { asyncHandler } from "../middleware/asyncHandler.js";
import type { RulesService } from "../services/rulesService.js";
import type { CreateRuleInput, ReplaceRuleInput, UpdateRuleInput } from "../types/rule.js";
import { parseEntityId } from "../utils/parseEntityId.js";

function routeId(req: Request): number {
  const id = req.params.id;
  const raw = Array.isArray(id) ? id[0]! : id!;
  return parseEntityId(raw);
}

export function createRulesRouter(service: RulesService): Router {
  const router = Router();

  router.get(
    "/",
    asyncHandler(async (_req, res) => {
      const rules = await service.list();
      res.json({ data: rules });
    }),
  );

  router.get(
    "/:id",
    asyncHandler(async (req, res) => {
      const rule = await service.getById(routeId(req));
      res.json({ data: rule });
    }),
  );

  router.post(
    "/",
    asyncHandler(async (req, res) => {
      const rule = await service.create(req.body as CreateRuleInput);
      res.status(201).json({ data: rule });
    }),
  );

  router.put(
    "/:id",
    asyncHandler(async (req, res) => {
      const rule = await service.replace(routeId(req), req.body as ReplaceRuleInput);
      res.json({ data: rule });
    }),
  );

  router.patch(
    "/:id",
    asyncHandler(async (req, res) => {
      const rule = await service.patch(routeId(req), req.body as UpdateRuleInput);
      res.json({ data: rule });
    }),
  );

  router.delete(
    "/:id",
    asyncHandler(async (req, res) => {
      await service.remove(routeId(req));
      res.status(204).send();
    }),
  );

  return router;
}
