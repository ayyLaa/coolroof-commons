import { ethers } from 'hardhat';
import { oracleRoundCostWei, sponsorRoundCostWei } from '../shared/round-cost';
import { networkName } from '../shared/spend-guard';

export interface WalletBudget { role: string; address: string; balanceWei: bigint; costWei: bigint }

export function shortfalls(wallets: readonly WalletBudget[]): string[] {
  return wallets
    .filter(wallet => wallet.balanceWei < wallet.costWei)
    .map(wallet => `${wallet.role} needs ${ethers.formatEther(wallet.costWei - wallet.balanceWei)} POL more`);
}

/**
 * Run before a round starts, so a round is never left half funded: the sponsor pays the
 * deposits and createProject gas, the oracle the storm roof's setup payment and one
 * submission per roof. Signer #0 is the sponsor and #1 the oracle, on Amoy (PRIVATE_KEY,
 * ORACLE_PRIVATE_KEY) as on the local node's test accounts.
 */
export async function checkRoundBudget(): Promise<void> {
  const [sponsor, oracle] = await ethers.getSigners();
  if (!sponsor || !oracle) throw new Error('Set PRIVATE_KEY and ORACLE_PRIVATE_KEY: both wallets pay for a round');
  // eth_gasPrice rather than getFeeData, which fires several requests at once: on Windows
  // Node then aborts at exit (a libuv assertion) and the shell script sees a failure.
  const { chainId } = await ethers.provider.getNetwork();
  const gasPrice = BigInt(await ethers.provider.send('eth_gasPrice', []));
  const wallets: WalletBudget[] = [
    { role: 'Sponsor', address: sponsor.address, balanceWei: await ethers.provider.getBalance(sponsor), costWei: sponsorRoundCostWei(gasPrice) },
    { role: 'Oracle', address: oracle.address, balanceWei: await ethers.provider.getBalance(oracle), costWei: oracleRoundCostWei(gasPrice) },
  ];
  console.log(`Network ${networkName(chainId)} (chain ${chainId}), gas price ${ethers.formatUnits(gasPrice, 'gwei')} gwei`);
  for (const wallet of wallets) {
    console.log(`  ${wallet.role.padEnd(8)}${wallet.address}  balance ${ethers.formatEther(wallet.balanceWei)} POL,`
      + ` one round costs about ${ethers.formatEther(wallet.costWei)} POL`);
  }
  const missing = shortfalls(wallets);
  if (missing.length) throw new Error(`Not enough POL for a full round: ${missing.join('; ')}. Nothing was sent.`);
  console.log('Both wallets can pay for a full round.');
}

// A script, not a hardhat task: as a task it trips a libuv assertion at exit on Windows,
// and scripts/demo-round.sh would read the exit code as a failed check.
if (require.main === module) {
  checkRoundBudget().catch((error: unknown) => {
    console.error(error instanceof Error ? error.message : error);
    process.exitCode = 1;
  });
}
