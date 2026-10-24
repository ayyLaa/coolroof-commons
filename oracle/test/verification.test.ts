import { afterEach, describe, it, expect, vi } from 'vitest';
import { VERIFICATION_STATUS } from '../../contracts/shared/status';
import { mapVerification, measuredAt, parsePhase } from '../src/verification';
import { VERIFICATION } from './fixtures';

afterEach(() => vi.restoreAllMocks());

describe('Backend verification mapping', () => {
  it('does not relabel a quality measurement as durability', () => {
    expect(() => mapVerification(VERIFICATION, 'ATH-0142', 'durability')).toThrow('measurement_phase');
  });

  it('rejects missing measurement identity', () => {
    expect(() => mapVerification({ ...VERIFICATION, measurement_id: undefined }, 'ATH-0142', 'quality')).toThrow('measurement_id');
  });

  it('refuses weather windows that do not cover the signed measurement', () => {
    expect(() => mapVerification({ ...VERIFICATION, weather: { ...VERIFICATION.weather,
      window_start: '2027-01-22T08:00:00Z' } }, 'ATH-0142', 'quality')).toThrow('weather window');
  });
  it.each(Object.entries(VERIFICATION_STATUS))('maps %s to the shared code %s', (status, code) => {
    const result = mapVerification({ ...VERIFICATION, status }, 'ATH-0142', 'quality');
    expect(result).toMatchObject({ status: code, normalizedDeltaCx10: -111n, coveragePct: 94, phase: 0 });
  });

  it('rounds temperatures, preserves evidence and maps durability', () => {
    const result = mapVerification({ ...VERIFICATION, normalized_delta_c: -3.26, force_majeure: true, measurement_phase: 'durability',
      evidence_hash: '12'.repeat(32) }, 'ATH-0142', 'durability');
    expect(result).toMatchObject({ normalizedDeltaCx10: -32n, phase: 1, forceMajeure: true,
      evidenceHash: VERIFICATION.evidence_hash, deviceSignature: '0x1234' });
  });

  it.each([
    { status: 'unknown' }, { status: '__proto__' }, { normalized_delta_c: null },
    { normalized_delta_c: Infinity }, { normalized_delta_c: 1e100 }, { coverage_pct: '94' },
    { coverage_pct: 101 }, { coverage_pct: -1 }, { force_majeure: 'false' },
    { evidence_hash: '0x1234' }, { device_signature: '0x123' }, { roof_id: 'another-roof' },
    { weather: null }, { weather: { max_gust_ms: -1 } },
  ])('rejects malformed data before any chain call: %j', changes => {
    expect(() => mapVerification({ ...VERIFICATION, ...changes }, 'ATH-0142', 'quality'))
      .toThrow('No transaction was sent');
  });

  it('rounds decimal coverage down and logs it', () => {
    const log = vi.spyOn(console, 'log').mockImplementation(() => undefined);
    expect(mapVerification({ ...VERIFICATION, coverage_pct: 93.5 }, 'ATH-0142', 'quality').coveragePct).toBe(93);
    expect(log).toHaveBeenCalledWith(expect.stringContaining('coverage_pct 93.5 for ATH-0142 rounded to 93'));
  });

  it.each([[84.5, 84], [85, 85]])('maps coverage %s conservatively to %s', (coverage, expected) => {
    expect(mapVerification({ ...VERIFICATION, coverage_pct: coverage }, 'ATH-0142', 'quality').coveragePct).toBe(expected);
  });

  it.each([[-7.99, -79n], [-8, -80n], [-8.01, -80n]])('maps delta %s conservatively to %s', (delta, expected) => {
    expect(mapVerification({ ...VERIFICATION, normalized_delta_c: delta }, 'ATH-0142', 'quality').normalizedDeltaCx10).toBe(expected);
  });

  it('scales the gust by ten and leaves rainfall to the weather lookup', () => {
    const result = mapVerification({ ...VERIFICATION, measurement_phase: 'durability', weather: { ...VERIFICATION.weather, precipitation_mm: 68.04 } }, 'ATH-0142', 'durability');
    expect(result).toMatchObject({ maxGustMsX10: 243n, precipMmX10: 680n });
    expect(measuredAt(VERIFICATION).toISOString()).toBe('2027-01-21T09:00:00.000Z');
    expect(() => measuredAt({ ...VERIFICATION, measured_at: 'yesterday' })).toThrow('measured_at');
  });

  it('rejects missing data, empty roof IDs and reserve as a verification phase', () => {
    expect(() => mapVerification(null, 'ATH-0142', 'quality')).toThrow('response object');
    expect(() => mapVerification(VERIFICATION, '', 'quality')).toThrow('must not be empty');
    expect(() => parsePhase('reserve')).toThrow('quality or durability');
  });
});
