import type { Filter, Log, Provider } from 'ethers';
import { EVENT_NAMES, escrowInterface } from './abi';
import { postEvent } from './backend';
import { createProvider } from './chain';
import { EVENT_DELIVERY_ATTEMPTS, EVENT_RETRY_BASE_MS, REPLAY_CHUNK_BLOCKS, loadConfig } from './config';
import { OracleError, errorMessage } from './errors';
import { decodeEvent } from './events';
import type { EventLog } from './events';

export type BlockTime = (blockNumber: number) => Promise<Date>;

const sleep = (ms: number): Promise<void> => new Promise(resolve => setTimeout(resolve, ms));

/** Retries with exponential backoff, so a backend restart during the demo loses no event. */
export async function withRetry<T>(send: () => Promise<T>, attempts = EVENT_DELIVERY_ATTEMPTS,
  baseDelayMs = EVENT_RETRY_BASE_MS): Promise<T> {
  for (let attempt = 1; ; attempt++) {
    try { return await send(); }
    catch (error: unknown) {
      if (attempt >= attempts) throw error;
      await sleep(baseDelayMs * 2 ** (attempt - 1));
    }
  }
}

/**
 * Keyed by eventId (block, transaction and log index), not by tx hash alone: a force
 * majeure transaction emits three events that must all arrive. The polling provider can
 * hand the same log over again after an RPC reconnect; the key keeps that from posting twice.
 */
export async function forwardEvent(backendUrl: string, log: EventLog, blockTime: BlockTime,
  seen: Set<string>): Promise<void> {
  const event = decodeEvent(log);
  if (!event || event.removed || seen.has(event.eventId)) return;
  seen.add(event.eventId);
  try {
    const occurredAt = await withRetry(() => blockTime(event.blockNumber));
    await withRetry(() => postEvent(backendUrl, event, occurredAt));
  } catch (error: unknown) {
    seen.delete(event.eventId);
    console.error(`${errorMessage(error)} Gave up after ${EVENT_DELIVERY_ATTEMPTS} attempts; event:`, JSON.stringify(event));
  }
}

/**
 * Posts one log at a time, in chain order: a tranche held and later released must reach
 * the backend in that order. The backend ignores events it already has, so replaying
 * history on every start is safe.
 */
export async function replayPastEvents(provider: Pick<Provider, 'getLogs'>, filter: Filter,
  range: { from: number; to: number }, forward: (log: Log) => Promise<void>): Promise<number> {
  let count = 0;
  for (let start = range.from; start <= range.to; start += REPLAY_CHUNK_BLOCKS) {
    const toBlock = Math.min(start + REPLAY_CHUNK_BLOCKS - 1, range.to);
    for (const log of await provider.getLogs({ ...filter, fromBlock: start, toBlock })) {
      await forward(log);
      count++;
    }
  }
  return count;
}

export async function startListener(): Promise<() => Promise<void>> {
  const config = loadConfig();
  const provider = createProvider(config.rpcUrl);
  const filter = { address: config.contractAddress, topics: [EVENT_NAMES.map(name => escrowInterface.getEvent(name)!.topicHash)] };
  const pending = new Set<Promise<void>>();
  const seen = new Set<string>();
  const blockTime: BlockTime = async blockNumber => {
    const block = await provider.getBlock(blockNumber);
    if (!block) throw new OracleError('RPC_FAILED', `Block ${blockNumber} is not available yet.`);
    return new Date(block.timestamp * 1000);
  };
  const handler = (log: Log): void => {
    const task = forwardEvent(config.backendUrl, log, blockTime, seen);
    pending.add(task);
    void task.finally(() => pending.delete(task));
  };
  try {
    if (await provider.getCode(config.contractAddress) === '0x') {
      throw new OracleError('CONFIG', 'No contract exists at CONTRACT_ADDRESS on the configured network.');
    }
    await provider.on('error', () => console.error('RPC event polling failed; retrying. Check AMOY_RPC_URL and connectivity.'));
    // Subscribed first, so nothing falls between the replay's last block and live events;
    // the seen set drops a log that arrives both ways.
    await provider.on(filter, handler);
    const latest = await provider.getBlockNumber();
    const replayed = await replayPastEvents(provider, filter, { from: config.eventsFromBlock, to: latest },
      log => forwardEvent(config.backendUrl, log, blockTime, seen));
    console.log(`Replayed ${replayed} past escrow events from block ${config.eventsFromBlock}.`);
    console.log(`Listening for escrow events at ${config.contractAddress}, forwarding to ${config.backendUrl}`);
  } catch (error: unknown) { provider.destroy(); throw error instanceof OracleError ? error
    : new OracleError('RPC_FAILED', 'Cannot start event listener. Check AMOY_RPC_URL and connectivity.'); }
  return async (): Promise<void> => {
    await provider.off(filter, handler);
    await Promise.allSettled([...pending]);
    provider.destroy();
  };
}

async function main(): Promise<void> {
  const stop = await startListener();
  const shutdown = (): void => { void stop().catch(() => { process.exitCode = 1; }); };
  process.once('SIGINT', shutdown);
  process.once('SIGTERM', shutdown);
}

if (require.main === module) {
  main().catch((error: unknown) => { console.error(errorMessage(error)); process.exitCode = 1; });
}
