import cors from 'cors';
import express from 'express';
import type { Express, NextFunction, Request, Response } from 'express';
import { parseRound } from '../../contracts/shared/demo-round';
import { TRANCHE_NAMES } from '../../contracts/shared/tranche';
import { readRoundBudget } from './chain';
import type { SubmissionResult } from './chain';
import { CORS_ORIGIN, EXPLORER_URL, loadConfig, SERVER_PORT } from './config';
import { OracleError, errorMessage } from './errors';
import { submitToChain } from './index';
import type { OracleResult } from './index';
import { roundBudgetReport } from './rounds';
import type { RoundBudget } from './rounds';
import type { Phase } from './verification';
import { requireOperator } from './security';

// Status codes for the failures the demo panel has to explain on screen.
const HTTP_STATUS: Record<string, number> = {
  INVALID_REQUEST: 422, INVALID_PHASE: 422, INVALID_ROOF: 422, INVALID_VERIFICATION: 422,
  BACKEND_UNAVAILABLE: 502, BACKEND_HTTP: 502, BACKEND_WEATHER: 502, RPC_FAILED: 502,
  INSUFFICIENT_GAS: 503, PROJECT_NOT_FOUND: 404, SPEND_NOT_ALLOWED: 403,
  PHASE_ALREADY_SETTLED: 409, PROJECT_CLOSED: 409, TRANSACTION_REVERTED: 409,
  CONFIRMATION_UNKNOWN: 504,
};
const SERVER_ERROR = 500;

export interface ServerDeps {
  submit: (roofId: string, phase: Phase, round?: number) => Promise<OracleResult>;
  budget: () => Promise<RoundBudget>;
  contractAddress: () => string;
}

const defaultDeps: ServerDeps = {
  submit: submitToChain,
  budget: () => readRoundBudget(loadConfig()),
  contractAddress: () => loadConfig().contractAddress,
};

/** The tranche the contract decided on: the one it paid, else the one it held. */
export function decision(result: SubmissionResult): { tranche: string | null; reason: string | null } {
  const decisive = result.events.find(event => event.event === 'TrancheReleased')
    ?? result.events.find(event => event.event === 'PaymentHeld');
  const { tranche, reason } = decisive?.data ?? {};
  return {
    tranche: typeof tranche === 'number' ? TRANCHE_NAMES[tranche] ?? null : null,
    reason: typeof reason === 'string' ? reason : null,
  };
}

function parseSubmission(body: unknown): { roofId: string; phase: Phase; round?: number } {
  const fields = typeof body === 'object' && body !== null ? body as Record<string, unknown> : {};
  if (typeof fields.roof_id !== 'string' || !fields.roof_id.trim()) {
    throw new OracleError('INVALID_REQUEST', 'roof_id is required, for example "ATH-0142".');
  }
  if (fields.phase !== 'quality' && fields.phase !== 'durability') {
    throw new OracleError('INVALID_REQUEST', 'phase must be "quality" or "durability".');
  }
  if (fields.round === undefined || fields.round === null) return { roofId: fields.roof_id, phase: fields.phase };
  try { return { roofId: fields.roof_id, phase: fields.phase, round: parseRound(fields.round) }; }
  catch { throw new OracleError('INVALID_REQUEST', 'round must be a whole number, 0 or more.'); }
}

function sendError(response: Response, error: unknown): void {
  const code = error instanceof OracleError ? error.code : 'INTERNAL';
  response.status(HTTP_STATUS[code] ?? SERVER_ERROR).json({ code: code.toLowerCase(), message: errorMessage(error) });
}

export function createApp(deps: ServerDeps = defaultDeps): Express {
  const app = express();
  app.use(cors({ origin: CORS_ORIGIN }));
  app.use(express.json());

  app.post('/submit', requireOperator, async (request: Request, response: Response) => {
    try {
      const { roofId, phase, round } = parseSubmission(request.body);
      const result = await deps.submit(roofId, phase, round);
      if (result.outcome === 'not_submitted') {
        response.json({ status: result.outcome, reason: result.reason, tranche: result.tranche,
          tx_hash: null, block_number: null, explorer_url: null });
        return;
      }
      response.json({
        tx_hash: result.transactionHash, status: result.outcome, ...decision(result),
        block_number: result.blockNumber, explorer_url: `${EXPLORER_URL}/tx/${result.transactionHash}`,
      });
    } catch (error: unknown) { sendError(response, error); }
  });

  app.get('/health', async (_request: Request, response: Response) => {
    try {
      const report = roundBudgetReport(await deps.budget());
      response.json({
        ok: true, contract_address: deps.contractAddress(), oracle_address: report.oracle.address,
        balance: report.oracle.balance, ...report,
      });
    } catch (error: unknown) { sendError(response, error); }
  });

  // Malformed JSON bodies reach here from express.json(); answer in the same error shape.
  app.use((_error: unknown, _request: Request, response: Response, _next: NextFunction) => {
    sendError(response, new OracleError('INVALID_REQUEST', 'The request body is not valid JSON.'));
  });
  return app;
}

if (require.main === module) {
  createApp().listen(SERVER_PORT, () => console.log(`Oracle HTTP server on http://localhost:${SERVER_PORT}`));
}
