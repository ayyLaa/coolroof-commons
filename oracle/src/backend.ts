import axios from 'axios';
import { parseRound, splitRoundRoofId } from '../../contracts/shared/demo-round';
import { TRANCHE_NAMES } from '../../contracts/shared/tranche';
import type { TrancheName } from '../../contracts/shared/tranche';
import { HTTP_TIMEOUT_MS } from './config';
import { OracleError } from './errors';
import type { ChainEvent } from './events';
import { DECIMAL_SCALE } from './verification';

/** The body of the backend's POST /contracts/{roof_id}/events (ContractEventCreate). */
export interface BackendEvent {
  event_name: ChainEvent['event']; tranche: TrancheName | null; amount_wei: string | null;
  tx_hash: string; block_number: number; reason: string | null; occurred_at: string;
  /** The demo round of the on-chain project; the roof ID in the URL carries no suffix. */
  round: number;
}

function backendMessage(error: unknown): string {
  if (!axios.isAxiosError(error)) return '';
  const data: unknown = error.response?.data;
  const message = typeof data === 'object' && data !== null ? (data as Record<string, unknown>).message : undefined;
  return typeof message === 'string' ? `: ${message.replace(/\.$/, '')}` : '';
}

/** The round the backend mirrors, so a submission without one goes to that round's projects. */
export async function fetchDemoRound(backendUrl: string): Promise<number> {
  let data: unknown;
  try {
    data = (await axios.get<unknown>(`${backendUrl}/demo/round`, { timeout: HTTP_TIMEOUT_MS })).data;
  } catch {
    throw new OracleError('BACKEND_UNAVAILABLE', 'Cannot read the current demo round from the backend. No transaction was sent.');
  }
  try { return parseRound((data as { round?: unknown } | null)?.round); }
  catch { throw new OracleError('BACKEND_HTTP', 'The backend returned no valid demo round. No transaction was sent.'); }
}

export async function fetchVerification(backendUrl: string, roofId: string): Promise<unknown> {
  try {
    const response = await axios.get<unknown>(`${backendUrl}/verification/${encodeURIComponent(roofId)}`, {
      timeout: HTTP_TIMEOUT_MS,
    });
    return response.data;
  } catch (error: unknown) {
    if (axios.isAxiosError(error) && error.response) {
      throw new OracleError('BACKEND_HTTP', `Backend verification request failed (HTTP ${error.response.status})${backendMessage(error)}. No transaction was sent.`);
    }
    throw new OracleError('BACKEND_UNAVAILABLE', 'Cannot reach the backend or the request timed out. Check BACKEND_URL and start the backend. No transaction was sent.');
  }
}

const unscaled = (x10: string | number): string => (Number(x10) / DECIMAL_SCALE).toFixed(1);

/** The storm readings live only in ForceMajeureApplied; the reason carries them to the
 * backend timeline, which has no columns for them. */
function eventReason(event: ChainEvent): string | null {
  const { reason, maxGustMsX10, precipMmX10 } = event.data;
  if (event.event === 'ForceMajeureApplied' && maxGustMsX10 !== undefined && precipMmX10 !== undefined) {
    return `gusts ${unscaled(maxGustMsX10)} m/s, ${unscaled(precipMmX10)} mm precipitation`;
  }
  return typeof reason === 'string' ? reason : null;
}

export function toBackendEvent(event: ChainEvent, occurredAt: Date): BackendEvent {
  const { tranche, amount } = event.data;
  return {
    event_name: event.event,
    tranche: typeof tranche === 'number' ? TRANCHE_NAMES[tranche] ?? null : null,
    amount_wei: typeof amount === 'string' ? amount : null,
    tx_hash: event.transactionHash, block_number: event.blockNumber,
    reason: eventReason(event), occurred_at: occurredAt.toISOString(),
    round: splitRoundRoofId(event.roofId).round,
  };
}

function isStaleRound(error: unknown): boolean {
  if (!axios.isAxiosError(error) || error.response?.status !== 409) return false;
  const data: unknown = error.response.data;
  return typeof data === 'object' && data !== null && (data as Record<string, unknown>).code === 'stale_round';
}

/**
 * Throws only when a retry can help (no connection, timeout, 5xx). A 4xx means the
 * backend refused this event as such (unknown roof, invalid body): it is logged with
 * the full body for manual replay and reported as rejected.
 */
export async function postEvent(backendUrl: string, event: ChainEvent, occurredAt: Date): Promise<'posted' | 'rejected' | 'stale'> {
  const body = toBackendEvent(event, occurredAt);
  const { roofId } = splitRoundRoofId(event.roofId);
  try {
    await axios.post(`${backendUrl}/contracts/${encodeURIComponent(roofId)}/events`, body, {
      timeout: HTTP_TIMEOUT_MS,
      ...(process.env.EVENT_API_KEY ? { headers: { 'X-API-Key': process.env.EVENT_API_KEY } } : {}),
    });
    return 'posted';
  } catch (error: unknown) {
    // Expected on every listener start: the replay walks through earlier rounds' events.
    if (isStaleRound(error)) {
      console.log(`Skipped ${event.event} for ${event.roofId}: not the backend's current demo round.`);
      return 'stale';
    }
    const status = axios.isAxiosError(error) ? error.response?.status : undefined;
    if (status !== undefined && status < 500) {
      console.error(`Backend rejected ${event.event} for ${event.roofId} (HTTP ${status})${backendMessage(error)}; not retried:`, JSON.stringify(body));
      return 'rejected';
    }
    throw new OracleError('EVENT_DELIVERY_FAILED', `Cannot deliver ${event.event} for ${event.roofId} to the backend${status ? ` (HTTP ${status})` : ''}.`);
  }
}
