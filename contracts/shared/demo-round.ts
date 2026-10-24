// Every escrow tranche pays once per project, so a demo can only be replayed on fresh
// projects. Each demo round funds its own projects under a suffixed key ("ATH-0142#3");
// the contract is unchanged, it only sees another roofId. Round 0 is the unsuffixed
// original that the local stack's chain-setup creates.
export const ROUND_SEPARATOR = '#';
export const ORIGINAL_ROUND = 0;

// The demo roofs every round funds, and the native tokens locked in each project. Amoy
// faucets hand out 0.1-0.5 POL a day, so the deposit is kept small enough that gas, not
// deposits, decides how many rounds a wallet can afford.
export const DEMO_ROOF_IDS = ['ATH-0142', 'ATH-0287', 'ATH-0355'] as const;
export const DEMO_DEPOSIT = '0.001';

/** Rejects anything but a whole, non-negative round number. */
export function parseRound(value: unknown): number {
  const round = typeof value === 'string' && /^\d+$/.test(value.trim()) ? Number(value) : value;
  if (typeof round !== 'number' || !Number.isSafeInteger(round) || round < ORIGINAL_ROUND) {
    throw new Error('round must be a whole number, 0 or more.');
  }
  return round;
}

export function roundRoofId(roofId: string, round: number): string {
  return round === ORIGINAL_ROUND ? roofId : `${roofId}${ROUND_SEPARATOR}${parseRound(round)}`;
}

/** The backend knows only the roof; the round travels next to it. */
export function splitRoundRoofId(chainRoofId: string): { roofId: string; round: number } {
  const index = chainRoofId.lastIndexOf(ROUND_SEPARATOR);
  const suffix = index < 0 ? '' : chainRoofId.slice(index + 1);
  if (!/^\d+$/.test(suffix)) return { roofId: chainRoofId, round: ORIGINAL_ROUND };
  return { roofId: chainRoofId.slice(0, index), round: Number(suffix) };
}
