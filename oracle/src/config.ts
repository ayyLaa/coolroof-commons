import dotenv from 'dotenv';
import path from 'node:path';
import { getAddress, isAddress, ZeroAddress } from 'ethers';
import { SPEND_FLAG } from '../../contracts/shared/spend-guard';
import { OracleError } from './errors';

// oracle/.env, seen from src/ under tsx and from dist/oracle/src/ once built (the build's
// rootDir is the repository so contracts/shared compiles alongside).
dotenv.config({ path: [path.resolve(__dirname, '../.env'), path.resolve(__dirname, '../../../.env')], quiet: true });

export interface OracleConfig { backendUrl: string; rpcUrl: string; contractAddress: string; eventsFromBlock: number }
export const HTTP_TIMEOUT_MS = 10_000;
export const RECEIPT_TIMEOUT_MS = 120_000;
// 1 + 2 + 4 + 8 s of backoff: rides out a backend restart without stalling the listener.
export const EVENT_DELIVERY_ATTEMPTS = 5;
export const EVENT_RETRY_BASE_MS = 1_000;
// Blocks per eth_getLogs call when replaying past events: public RPCs cap the range.
export const REPLAY_CHUNK_BLOCKS = 5_000;
export const SERVER_PORT = Number(process.env.ORACLE_PORT ?? 4020);
// The Vite dev server the demo panel runs on.
export const CORS_ORIGIN = process.env.ORACLE_CORS_ORIGIN ?? 'http://localhost:5173';
export const EXPLORER_URL = (process.env.EXPLORER_URL ?? 'https://amoy.polygonscan.com').replace(/\/+$/, '');

function httpUrl(value: string | undefined, name: string): string {
  try {
    const url = new URL(value ?? '');
    if (!['http:', 'https:'].includes(url.protocol)) throw new Error('Invalid protocol');
    return url.toString().replace(/\/+$/, '');
  } catch { throw new OracleError('CONFIG', `${name} must be a valid HTTP or HTTPS URL.`); }
}

// The listener replays events from this block on startup, so what happened before it
// started (setup-demo pays the storm roof's quality tranche) still reaches the backend.
// 0 suits a local chain; on Amoy set EVENTS_FROM_BLOCK to the escrow's deployment block.
function blockNumber(value: string | undefined, name: string): number {
  const block = Number(value ?? 0);
  if (!Number.isSafeInteger(block) || block < 0) throw new OracleError('CONFIG', `${name} must be a block number.`);
  return block;
}

export function loadConfig(): OracleConfig {
  const address = process.env.CONTRACT_ADDRESS;
  if (!address || !isAddress(address) || address === ZeroAddress) {
    throw new OracleError('CONFIG', 'CONTRACT_ADDRESS must be a nonzero Ethereum address.');
  }
  return {
    backendUrl: httpUrl(process.env.BACKEND_URL, 'BACKEND_URL'),
    rpcUrl: httpUrl(process.env.AMOY_RPC_URL, 'AMOY_RPC_URL'),
    contractAddress: getAddress(address),
    eventsFromBlock: blockNumber(process.env.EVENTS_FROM_BLOCK, 'EVENTS_FROM_BLOCK'),
  };
}

/** ALLOW_MAINNET_SPEND: transactions on any chain but a local one need it set to true. */
export function spendFlag(): string | undefined {
  return process.env[SPEND_FLAG];
}

export function loadPrivateKey(): string {
  const key = process.env.ORACLE_PRIVATE_KEY;
  if (!key || !/^(0x)?[0-9a-fA-F]{64}$/.test(key)) {
    throw new OracleError('CONFIG', 'ORACLE_PRIVATE_KEY must contain a valid 32-byte private key.');
  }
  return key.startsWith('0x') ? key : `0x${key}`;
}
