import { formatEther, formatUnits } from 'ethers';
import { oracleRoundCostWei, roundsLeft, sponsorRoundCostWei } from '../../contracts/shared/round-cost';
import { networkName } from '../../contracts/shared/spend-guard';
import type { NetworkName } from '../../contracts/shared/spend-guard';
import type { OracleAccount } from './chain';

export interface RoundBudget {
  sponsor: OracleAccount; oracle: OracleAccount; gasPriceWei: bigint; chainId: bigint;
}

function wallet(account: OracleAccount, costWei: bigint) {
  return {
    address: account.address, balance: formatEther(account.balanceWei),
    round_cost: formatEther(costWei), rounds_left: roundsLeft(account.balanceWei, costWei),
  };
}

/** The /health view: how many more demo rounds each wallet can pay for at today's gas price. */
export function roundBudgetReport(budget: RoundBudget): {
  network: NetworkName; chain_id: number; gas_price_gwei: string;
  sponsor: ReturnType<typeof wallet>; oracle: ReturnType<typeof wallet>;
} {
  return {
    network: networkName(budget.chainId),
    chain_id: Number(budget.chainId),
    gas_price_gwei: formatUnits(budget.gasPriceWei, 'gwei'),
    sponsor: wallet(budget.sponsor, sponsorRoundCostWei(budget.gasPriceWei)),
    oracle: wallet(budget.oracle, oracleRoundCostWei(budget.gasPriceWei)),
  };
}
