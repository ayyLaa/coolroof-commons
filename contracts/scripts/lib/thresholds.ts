import thresholds from '../../../schema/thresholds.json';

// The repository's schema/thresholds.json is the single source; the backend reads the same
// file. Solidity has no decimals, so the escrow takes Celsius deltas multiplied by ten:
// this is the only place that conversion happens.
const CELSIUS_TO_X10 = 10;
const SECONDS_PER_DAY = 24 * 60 * 60;

type CityThresholds = Partial<typeof thresholds.default>;

export interface EscrowThresholds {
  minNormalizedDeltaCx10: number;
  minCoveragePct: number;
}

function forCity(city: string): typeof thresholds.default {
  const overrides = (thresholds.by_city as Record<string, CityThresholds>)[city.toLowerCase()] ?? {};
  return { ...thresholds.default, ...overrides };
}

export function escrowThresholds(city: string): EscrowThresholds {
  const merged = forCity(city);
  return {
    minNormalizedDeltaCx10: Math.round(merged.min_normalized_delta_c * CELSIUS_TO_X10),
    minCoveragePct: merged.min_coverage_pct,
  };
}

/** What CoolRoofEscrow.DURABILITY_DELAY must equal; the contract cannot read JSON. */
export function durabilityDelaySeconds(): bigint {
  return BigInt(thresholds.default.durability_check_days * SECONDS_PER_DAY);
}
