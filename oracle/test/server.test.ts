import type { AddressInfo } from 'node:net';
import type { Server } from 'node:http';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createApp } from '../src/server';
import type { ServerDeps } from '../src/server';
import { OracleError } from '../src/errors';
import { decodeEvent } from '../src/events';
import { ADDRESS, eventLog, TX_HASH } from './fixtures';

const SPONSOR = '0x2222222222222222222222222222222222222222';
const deps = { submit: vi.fn(), budget: vi.fn(), contractAddress: () => ADDRESS } satisfies ServerDeps;
let server: Server;
let base: string;

beforeEach(async () => {
  vi.resetAllMocks();
  server = createApp(deps).listen(0);
  await new Promise(resolve => server.once('listening', resolve));
  base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
});
afterEach(() => new Promise<void>(resolve => server.close(() => resolve())));

function submit(body: unknown): Promise<Response> {
  return fetch(`${base}/submit`, {
    method: 'POST', headers: { 'content-type': 'application/json', origin: 'http://localhost:5173' },
    body: typeof body === 'string' ? body : JSON.stringify(body),
  });
}

describe('Oracle HTTP server', () => {
  it('refuses protected writes without an operator key before submitting', async () => {
    vi.stubEnv('WRITE_API_KEY', 'operator-test-key');
    try {
      const response = await submit({ roof_id: 'ATH-0142', phase: 'quality' });
      expect(response.status).toBe(401);
      expect(deps.submit).not.toHaveBeenCalled();
    } finally { vi.unstubAllEnvs(); }
  });

  it('fails closed outside local mode when no key is configured', async () => {
    vi.stubEnv('APP_MODE', 'production');
    vi.stubEnv('WRITE_API_KEY', '');
    try {
      expect((await submit({ roof_id: 'ATH-0142', phase: 'quality' })).status).toBe(503);
      expect(deps.submit).not.toHaveBeenCalled();
    } finally { vi.unstubAllEnvs(); }
  });
  it('reports a refused verification without inventing a transaction', async () => {
    deps.submit.mockResolvedValue({ outcome: 'not_submitted', transactionHash: null, blockNumber: null,
      events: [], tranche: 'QUALITY', reason: 'Not submitted: status is flagged. No payment was attempted.' });
    expect(await (await submit({ roof_id: 'ATH-0142', phase: 'quality' })).json()).toEqual({
      status: 'not_submitted', tx_hash: null, block_number: null, explorer_url: null, tranche: 'QUALITY',
      reason: 'Not submitted: status is flagged. No payment was attempted.',
    });
  });
  it('submits and reports the decision with an explorer link', async () => {
    const events = [decodeEvent(eventLog('TrancheReleased', ['ATH-0142', 0, 600n, ADDRESS]))!];
    deps.submit.mockResolvedValue({ transactionHash: TX_HASH, blockNumber: 42, outcome: 'released', events });
    const response = await submit({ roof_id: 'ATH-0142', phase: 'quality' });
    expect(response.status).toBe(200);
    expect(response.headers.get('access-control-allow-origin')).toBe('http://localhost:5173');
    expect(await response.json()).toEqual({
      tx_hash: TX_HASH, status: 'released', tranche: 'QUALITY', reason: null,
      block_number: 42, explorer_url: `https://amoy.polygonscan.com/tx/${TX_HASH}`,
    });
    expect(deps.submit).toHaveBeenCalledWith('ATH-0142', 'quality', undefined);
  });

  it('passes a requested demo round on to the chain submission', async () => {
    const events = [decodeEvent(eventLog('TrancheReleased', ['ATH-0142#3', 0, 600n, ADDRESS]))!];
    deps.submit.mockResolvedValue({ transactionHash: TX_HASH, blockNumber: 42, outcome: 'released', events });
    expect((await submit({ roof_id: 'ATH-0142', phase: 'quality', round: 3 })).status).toBe(200);
    expect(deps.submit).toHaveBeenCalledWith('ATH-0142', 'quality', 3);
  });

  it('names the held tranche and why', async () => {
    const events = [decodeEvent(eventLog('PaymentHeld', ['ATH-0287', 0, 'Measurement thresholds not met']))!];
    deps.submit.mockResolvedValue({ transactionHash: TX_HASH, blockNumber: 42, outcome: 'held', events });
    expect(await (await submit({ roof_id: 'ATH-0287', phase: 'quality' })).json())
      .toMatchObject({ status: 'held', tranche: 'QUALITY', reason: 'Measurement thresholds not met' });
  });

  it.each([
    [new OracleError('BACKEND_UNAVAILABLE', 'Cannot reach the backend.'), 502],
    [new OracleError('INSUFFICIENT_GAS', 'Oracle wallet has insufficient native tokens for gas.'), 503],
    [new OracleError('TRANSACTION_REVERTED', 'Contract rejected the verification.'), 409],
    [new OracleError('PROJECT_NOT_FOUND', 'No escrow project exists on chain for this roof.'), 404],
  ])('turns %s into readable JSON', async (error, status) => {
    deps.submit.mockRejectedValue(error);
    const response = await submit({ roof_id: 'ATH-0142', phase: 'quality' });
    expect(response.status).toBe(status);
    expect(await response.json()).toEqual({ code: error.code.toLowerCase(), message: error.message });
  });

  it('rejects bad requests without calling the chain', async () => {
    for (const body of [
      { phase: 'quality' }, { roof_id: 'ATH-0142', phase: 'reserve' }, '{not json',
      { roof_id: 'ATH-0142', phase: 'quality', round: -1 }, { roof_id: 'ATH-0142', phase: 'quality', round: 1.5 },
    ]) {
      const response = await submit(body);
      expect(response.status).toBe(422);
      expect((await response.json()).code).toBe('invalid_request');
    }
    expect(deps.submit).not.toHaveBeenCalled();
  });

  it('reports health with both wallets and the demo rounds each can still pay for', async () => {
    deps.budget.mockResolvedValue({
      oracle: { address: ADDRESS, balanceWei: 1_500_000_000_000_000_000n },
      sponsor: { address: SPONSOR, balanceWei: 54_000_000_000_000_000n },
      gasPriceWei: 30_000_000_000n,
      chainId: 80002n,
    });
    const body = await (await fetch(`${base}/health`)).json();
    expect(body).toMatchObject({
      ok: true, contract_address: ADDRESS, oracle_address: ADDRESS, balance: '1.5', gas_price_gwei: '30.0',
      network: 'amoy', chain_id: 80002,
    });
    // 3 x (0.001 deposit + 253,000 gas x 30 gwei) = 0.02577 POL a round.
    expect(body.sponsor).toEqual({ address: SPONSOR, balance: '0.054', round_cost: '0.02577', rounds_left: 2 });
    expect(body.oracle.rounds_left).toBe(64);
  });

  it('reports an unreachable RPC on the health check', async () => {
    deps.budget.mockRejectedValue(new OracleError('RPC_FAILED', 'Cannot read the wallet balances.'));
    const response = await fetch(`${base}/health`);
    expect(response.status).toBe(502);
    expect((await response.json()).code).toBe('rpc_failed');
  });
});
