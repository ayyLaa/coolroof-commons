// Every transaction the contract scripts or the oracle send passes through here first. A
// local Hardhat chain spends nothing worth keeping; anywhere else the scarce faucet POL
// (or, on a mainnet, real money) is spent only with ALLOW_MAINNET_SPEND=true.
export const LOCAL_CHAIN_ID = 31337n;
export const AMOY_CHAIN_ID = 80002n;
export const SPEND_FLAG = 'ALLOW_MAINNET_SPEND';
export const AMOY_SPEND_REFUSED =
  `Refusing to spend real POL on Amoy. Set ${SPEND_FLAG}=true to proceed.`;

export type NetworkName = 'local' | 'amoy' | 'other';

export function networkName(chainId: bigint): NetworkName {
  if (chainId === LOCAL_CHAIN_ID) return 'local';
  return chainId === AMOY_CHAIN_ID ? 'amoy' : 'other';
}

/** Returns the reason to refuse, or null when the transaction may be sent. */
export function spendRefusal(chainId: bigint, flag: string | undefined): string | null {
  if (chainId === LOCAL_CHAIN_ID || flag?.trim().toLowerCase() === 'true') return null;
  if (chainId === AMOY_CHAIN_ID) return AMOY_SPEND_REFUSED;
  return `Refusing to spend on chain ${chainId}. Set ${SPEND_FLAG}=true to proceed.`;
}
