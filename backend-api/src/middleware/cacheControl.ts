import type { NextFunction, Request, Response } from "express";

/**
 * Sets Cache-Control on successful GET responses so browsers and proxies
 * can reuse payloads for a short window (aligned with server-side TTL).
 */
export function cacheControl(maxAgeSeconds: number) {
  if (maxAgeSeconds <= 0) {
    return (_req: Request, _res: Response, next: NextFunction) => next();
  }

  const header = `private, max-age=${maxAgeSeconds}`;

  return (req: Request, res: Response, next: NextFunction): void => {
    if (req.method !== "GET") {
      next();
      return;
    }

    const originalJson = res.json.bind(res);
    res.json = function jsonWithCache(body?: unknown) {
      if (res.statusCode >= 200 && res.statusCode < 300) {
        res.setHeader("Cache-Control", header);
      }
      return originalJson(body);
    };

    next();
  };
}
