import type { CoolRoofEscrow } from '../typechain-types';

export interface TrancheAmounts { quality: bigint; durability: bigint; reserve: bigint }

// Read from the escrow's own constants, so the expected split never drifts from the
// contract; rounding dust goes to the reserve there too, keeping the sum the deposit.
export async function trancheAmounts(escrow: CoolRoofEscrow, deposit: bigint): Promise<TrancheAmounts> {
  const base = await escrow.PERCENT_BASE();
  const quality = deposit * await escrow.QUALITY_PERCENT() / base;
  const durability = deposit * await escrow.DURABILITY_PERCENT() / base;
  return { quality, durability, reserve: deposit - quality - durability };
}
