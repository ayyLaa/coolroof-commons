import { isError } from 'ethers';
import { escrowInterface } from './abi';
import { OracleError } from './errors';

function rpcMessage(error: unknown): string {
  if (typeof error !== 'object' || error === null) return '';
  const record = error as Record<string, unknown>;
  const own = typeof record.message === 'string' ? record.message : '';
  const nested = typeof record.info === 'object' && record.info !== null
    ? (record.info as Record<string, unknown>).error : record.error;
  return `${own} ${nested === error ? '' : rpcMessage(nested)}`.toLowerCase();
}

export function chainError(error: unknown, transactionHash?: string): OracleError {
  if (error instanceof OracleError) return error;
  const hash = transactionHash ? ` Transaction: ${transactionHash}.` : '';
  if (isError(error, 'INSUFFICIENT_FUNDS') || /insufficient funds|not enough funds/.test(rpcMessage(error))) {
    return new OracleError('INSUFFICIENT_GAS', 'Oracle wallet has insufficient native tokens for gas. Fund the oracle wallet and retry.');
  }
  if (isError(error, 'CALL_EXCEPTION')) return revertError(revertName(error.data), hash);
  if (transactionHash) {
    return new OracleError('CONFIRMATION_UNKNOWN', `Transaction was broadcast but confirmation could not be determined. Check its receipt before retrying.${hash}`);
  }
  return new OracleError('RPC_FAILED', 'Blockchain request failed. Check AMOY_RPC_URL and RPC connectivity before retrying.');
}

const KNOWN_REVERTS: Record<string, [code: string, message: string]> = {
  ProjectNotFound: ['PROJECT_NOT_FOUND', 'No escrow project exists on chain for this roof in the current demo round. Run scripts/demo-round.sh to fund one.'],
  PhaseAlreadySettled: ['PHASE_ALREADY_SETTLED', 'This tranche is already settled on chain and cannot be paid twice.'],
  ProjectClosed: ['PROJECT_CLOSED', 'The sponsor has reclaimed this project; it accepts no more verifications.'],
  UnauthorizedOracle: ['UNAUTHORIZED_ORACLE', 'This oracle wallet is not the escrow oracle. Check ORACLE_PRIVATE_KEY and setOracle.'],
};

function revertError(name: string | undefined, hash: string): OracleError {
  const known = name ? KNOWN_REVERTS[name] : undefined;
  if (known) return new OracleError(known[0], `${known[1]} (${name})${hash}`);
  return new OracleError('TRANSACTION_REVERTED', `Contract rejected the verification${name ? ` (${name})` : ''}. Check oracle permissions, project ID and tranche state.${hash}`);
}

function revertName(data: string | null): string | undefined {
  if (!data) return undefined;
  try { return escrowInterface.parseError(data)?.name; }
  catch { return undefined; }
}
