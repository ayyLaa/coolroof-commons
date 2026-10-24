import { timingSafeEqual } from 'node:crypto';
import type { NextFunction, Request, Response } from 'express';

export function requireOperator(request: Request, response: Response, next: NextFunction): void {
  const expected = process.env.WRITE_API_KEY ?? '';
  if (!expected) {
    if ((process.env.APP_MODE ?? 'local') === 'local') { next(); return; }
    response.status(503).json({ code: 'security_unavailable', message: 'WRITE_API_KEY must be configured outside local mode.' });
    return;
  }
  const actual = Buffer.from(request.header('X-API-Key') ?? '');
  const desired = Buffer.from(expected);
  if (actual.length !== desired.length || !timingSafeEqual(actual, desired)) {
    response.status(401).json({ code: 'unauthorized', message: 'A valid API key is required for this operation.' });
    return;
  }
  next();
}
