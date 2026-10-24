import { escrowInterface } from '../src/abi';
import type { EventLog } from '../src/events';

export const ADDRESS = '0x1111111111111111111111111111111111111111';
export const TX_HASH = `0x${'ab'.repeat(32)}`;
export const BLOCK_HASH = `0x${'cd'.repeat(32)}`;
export const VERIFICATION = {
  measurement_id: '11111111-1111-4111-8111-111111111111', measurement_phase: 'after',
  roof_id: 'ATH-0142', status: 'approved', normalized_delta_c: -11.1,
  coverage_pct: 94, force_majeure: false, evidence_hash: `0x${'12'.repeat(32)}`, device_signature: '0x1234',
  measured_at: '2027-01-21T09:00:00Z',
  weather: { ambient_c: 19, radiation_wm2: 150, wind_ms: 14, max_gust_ms: 24.3, precipitation_mm: 0, window_start: '2027-01-21T08:00:00Z', window_end: '2027-01-21T10:00:00Z' },
};

export function eventLog(name: string, values: readonly unknown[], index = 0): EventLog {
  const fragment = escrowInterface.getEvent(name)!;
  const encoded = escrowInterface.encodeEventLog(fragment, values);
  return {
    ...encoded, address: ADDRESS, transactionHash: TX_HASH, blockHash: BLOCK_HASH,
    blockNumber: 42, index, removed: false,
  };
}
