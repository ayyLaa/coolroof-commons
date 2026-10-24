import { id, isHexString } from 'ethers';
import { ROUND_SEPARATOR } from '../../contracts/shared/demo-round';
import { FORCE_MAJEURE_STATUS, VERIFICATION_STATUS } from '../../contracts/shared/status';
import { OracleError } from './errors';

export type Phase = 'quality' | 'durability';
const PHASE_CODES = { quality: 0, durability: 1 } as const;
// Solidity has no decimals: Celsius deltas, gusts and rainfall go on chain multiplied by ten.
export const DECIMAL_SCALE = 10;
const MAX_COVERAGE = 100;

export interface ChainVerification {
  roofId: string; status: number; normalizedDeltaCx10: bigint; coveragePct: number;
  forceMajeure: boolean; phase: number; evidenceHash: string; deviceSignature: string;
  maxGustMsX10: bigint; precipMmX10: bigint;
  measurementId: string; measuredAt: bigint;
}

function invalid(field: string): never {
  throw new OracleError('INVALID_VERIFICATION', `Backend verification has an invalid ${field}. No transaction was sent.`);
}

export function parsePhase(value: string): Phase {
  if (value !== 'quality' && value !== 'durability') {
    throw new OracleError('INVALID_PHASE', 'Phase must be quality or durability.');
  }
  return value;
}

export function validateRoofId(roofId: string): void {
  if (!roofId.trim()) throw new OracleError('INVALID_ROOF', 'Roof ID must not be empty.');
  if (roofId.includes(ROUND_SEPARATOR)) {
    throw new OracleError('INVALID_ROOF', `Pass the demo round separately, not as "${ROUND_SEPARATOR}" in the roof ID.`);
  }
}

function hexField(value: unknown, field: string, size?: number): string {
  if (typeof value !== 'string') return invalid(field);
  const hex = value.startsWith('0x') ? value : `0x${value}`;
  if (!isHexString(hex, size ?? true)) return invalid(field);
  return hex;
}

function scaledField(value: unknown, field: string, allowNegative: boolean): bigint {
  if (typeof value !== 'number' || !Number.isFinite(value) || (!allowNegative && value < 0)) return invalid(field);
  // Move cooling toward zero; never turn a failing delta into passing cooling.
  // Weather is rounded down so it cannot invent a threshold-exceeding storm.
  const scaled = allowNegative ? Math.ceil(value * DECIMAL_SCALE) : Math.floor(value * DECIMAL_SCALE);
  if (!Number.isSafeInteger(scaled)) return invalid(field);
  return BigInt(scaled);
}

// The escrow compares coverage with an integer percent threshold (uint256), so the
// backend's decimal value is rounded down so failed coverage cannot pass on chain.
function coverageField(value: unknown, roofId: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0 || value > MAX_COVERAGE) {
    return invalid('coverage_pct');
  }
  const rounded = Math.floor(value);
  if (rounded !== value) console.log(`coverage_pct ${value} for ${roofId} rounded to ${rounded} for the contract.`);
  return rounded;
}

export function measuredAt(data: unknown): Date {
  const value = typeof data === 'object' && data !== null ? (data as Record<string, unknown>).measured_at : undefined;
  const date = typeof value === 'string' ? new Date(value) : undefined;
  if (!date || Number.isNaN(date.getTime())) return invalid('measured_at');
  return date;
}

function requireWeatherWindow(weather: Record<string, unknown>, measurement: Date): void {
  const start = typeof weather.window_start === 'string' ? Date.parse(weather.window_start) : NaN;
  const end = typeof weather.window_end === 'string' ? Date.parse(weather.window_end) : NaN;
  if (!Number.isFinite(start) || !Number.isFinite(end) || start > end
    || measurement.getTime() < start || measurement.getTime() > end) return invalid('weather window');
}

export function mapVerification(data: unknown, roofId: string, phase: Phase): ChainVerification {
  validateRoofId(roofId);
  if (typeof data !== 'object' || data === null) return invalid('response object');
  const fields = data as Record<string, unknown>;
  if (fields.roof_id !== undefined && fields.roof_id !== roofId) return invalid('roof_id');
  if (typeof fields.status !== 'string' || !Object.hasOwn(VERIFICATION_STATUS, fields.status)) return invalid('status');
  if (typeof fields.force_majeure !== 'boolean') return invalid('force_majeure');
  if (fields.measurement_phase !== (phase === 'quality' ? 'after' : 'durability')) return invalid('measurement_phase');
  if (typeof fields.measurement_id !== 'string' || !/^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(fields.measurement_id)) return invalid('measurement_id');
  const weather = typeof fields.weather === 'object' && fields.weather !== null
    ? fields.weather as Record<string, unknown> : invalid('weather');
  requireWeatherWindow(weather, measuredAt(data));
  return {
    roofId, status: fields.force_majeure && fields.status === 'insufficient_data'
      ? FORCE_MAJEURE_STATUS : VERIFICATION_STATUS[fields.status as keyof typeof VERIFICATION_STATUS],
    normalizedDeltaCx10: scaledField(fields.normalized_delta_c, 'normalized_delta_c', true),
    coveragePct: coverageField(fields.coverage_pct, roofId),
    forceMajeure: fields.force_majeure, phase: PHASE_CODES[parsePhase(phase)],
    evidenceHash: hexField(fields.evidence_hash, 'evidence_hash', 32),
    deviceSignature: hexField(fields.device_signature, 'device_signature'),
    maxGustMsX10: scaledField(weather.max_gust_ms, 'weather.max_gust_ms', false),
    precipMmX10: scaledField(weather.precipitation_mm, 'weather.precipitation_mm', false),
    measurementId: id(fields.measurement_id.toLowerCase()),
    measuredAt: BigInt(Math.floor(measuredAt(data).getTime() / 1000)),
  };
}
