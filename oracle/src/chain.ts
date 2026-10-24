import { Contract, FetchRequest, JsonRpcProvider, Wallet } from 'ethers';
import type { TransactionReceipt, TransactionResponse } from 'ethers';
import { ESCROW_ABI } from './abi';
import { chainError } from './chain-errors';
import { spendRefusal } from '../../contracts/shared/spend-guard';
import { HTTP_TIMEOUT_MS, loadPrivateKey, RECEIPT_TIMEOUT_MS, spendFlag } from './config';
import type { OracleConfig } from './config';
import { OracleError } from './errors';
import { decodeEvent } from './events';
import type { ChainEvent } from './events';
import type { RoundBudget } from './rounds';
import type { ChainVerification } from './verification';

export interface SubmissionResult {
  transactionHash: string; blockNumber: number;
  outcome: 'released' | 'held' | 'force_majeure' | 'confirmed'; events: ChainEvent[];
}

export function createProvider(rpcUrl: string): JsonRpcProvider {
  const request = new FetchRequest(rpcUrl);
  request.timeout = HTTP_TIMEOUT_MS;
  return new JsonRpcProvider(request, undefined, { polling: true });
}

function receiptResult(receipt: TransactionReceipt, address: string): SubmissionResult {
  const events = receipt.logs.filter(log => log.address.toLowerCase() === address.toLowerCase())
    .map(decodeEvent).filter((event): event is ChainEvent => event !== null);
  const names = events.map(event => event.event);
  const outcome = names.includes('ForceMajeureApplied') ? 'force_majeure'
    : names.includes('TrancheReleased') ? 'released' : names.includes('PaymentHeld') ? 'held' : 'confirmed';
  return { transactionHash: receipt.hash, blockNumber: receipt.blockNumber, outcome, events };
}

export async function sendVerification(config: OracleConfig, value: ChainVerification): Promise<SubmissionResult> {
  const privateKey = loadPrivateKey();
  const provider = createProvider(config.rpcUrl);
  let transactionHash: string | undefined;
  try {
    let wallet: Wallet;
    try { wallet = new Wallet(privateKey, provider); }
    catch { throw new OracleError('CONFIG', 'ORACLE_PRIVATE_KEY is not a valid signing key.'); }
    // Checked before anything is signed: a wrong AMOY_RPC_URL must not spend faucet POL.
    const refusal = spendRefusal((await provider.getNetwork()).chainId, spendFlag());
    if (refusal) throw new OracleError('SPEND_NOT_ALLOWED', refusal);
    if (await provider.getCode(config.contractAddress) === '0x') {
      throw new OracleError('CONFIG', 'No contract exists at CONTRACT_ADDRESS on the configured network.');
    }
    const contract = new Contract(config.contractAddress, ESCROW_ABI, wallet);
    const transaction: TransactionResponse = await contract.getFunction('submitVerification')(
      value.roofId, value.status, value.normalizedDeltaCx10, value.coveragePct,
      value.forceMajeure, value.phase, value.evidenceHash, value.deviceSignature,
      value.maxGustMsX10, value.precipMmX10,
      value.measurementId, value.measuredAt,
    );
    transactionHash = transaction.hash;
    const receipt = await transaction.wait(1, RECEIPT_TIMEOUT_MS);
    if (!receipt) throw new OracleError('CONFIRMATION_UNKNOWN', `Transaction ${transactionHash} is not confirmed. Check its receipt before retrying.`);
    if (receipt.status !== 1) throw new OracleError('TRANSACTION_REVERTED', `Transaction reverted: ${receipt.hash}`);
    return receiptResult(receipt, config.contractAddress);
  } catch (error: unknown) { throw chainError(error, transactionHash); }
  finally { provider.destroy(); }
}

export interface OracleAccount { address: string; balanceWei: bigint }

/** The sponsor is read as the escrow's owner: deploy.ts deploys from the sponsor key, so
 * no extra setting can drift from the chain. */
export async function readRoundBudget(config: OracleConfig): Promise<RoundBudget> {
  const provider = createProvider(config.rpcUrl);
  try {
    const oracle = new Wallet(loadPrivateKey()).address;
    const sponsor = String(await new Contract(config.contractAddress, ESCROW_ABI, provider).getFunction('owner')());
    const [oracleWei, sponsorWei, fees, network] = await Promise.all([
      provider.getBalance(oracle), provider.getBalance(sponsor), provider.getFeeData(), provider.getNetwork(),
    ]);
    return {
      oracle: { address: oracle, balanceWei: oracleWei }, sponsor: { address: sponsor, balanceWei: sponsorWei },
      gasPriceWei: fees.gasPrice ?? 0n, chainId: network.chainId,
    };
  } catch (error: unknown) {
    if (error instanceof OracleError) throw error;
    throw new OracleError('RPC_FAILED', 'Cannot read the wallet balances. Check AMOY_RPC_URL, CONTRACT_ADDRESS and connectivity.');
  } finally { provider.destroy(); }
}
