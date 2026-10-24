import { DEMO_DEPOSIT, DEMO_ROOF_IDS } from './demo-round';

// What one demo round costs each wallet: the oracle's /health reports it and
// scripts/demo-round.sh checks it before starting, so a round is never left half funded.
// Gas measured on Amoy for CoolRoofEscrow (createProject 230,089; submitVerification
// 177,211), plus 10% so a slightly costlier call still fits.
export const CREATE_PROJECT_GAS = 253_000n;
export const SUBMIT_VERIFICATION_GAS = 195_000n;
const PROJECTS_PER_ROUND = BigInt(DEMO_ROOF_IDS.length);
// setup-demo pays the storm roof's quality tranche as the oracle, then the demo submits
// once per roof.
const ORACLE_SUBMISSIONS_PER_ROUND = PROJECTS_PER_ROUND + 1n;

const WEI_DECIMALS = 18;

/** "0.001" in native tokens to wei. Written out instead of ethers.parseEther: the oracle
 * image ships contracts/shared without node_modules, so this folder imports nothing. */
export function tokensToWei(value: string): bigint {
  const parts = value.trim().split('.');
  const [whole, fraction = ''] = parts;
  if (parts.length > 2 || !/^\d+$/.test(whole) || !/^\d*$/.test(fraction) || fraction.length > WEI_DECIMALS) {
    throw new Error(`Not a token amount: ${value}`);
  }
  return BigInt(whole + fraction.padEnd(WEI_DECIMALS, '0'));
}

/** Deposits plus the createProject gas the sponsor pays for one round's projects. */
export function sponsorRoundCostWei(gasPriceWei: bigint): bigint {
  return PROJECTS_PER_ROUND * (tokensToWei(DEMO_DEPOSIT) + CREATE_PROJECT_GAS * gasPriceWei);
}

export function oracleRoundCostWei(gasPriceWei: bigint): bigint {
  return ORACLE_SUBMISSIONS_PER_ROUND * SUBMIT_VERIFICATION_GAS * gasPriceWei;
}

export function roundsLeft(balanceWei: bigint, costWei: bigint): number {
  return costWei > 0n ? Number(balanceWei / costWei) : 0;
}
