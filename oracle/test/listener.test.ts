import { afterEach, describe, expect, it, vi } from 'vitest';
import { forwardEvent, replayPastEvents, startListener, withRetry } from '../src/listener';
import { postEvent } from '../src/backend';
import { ADDRESS, eventLog } from './fixtures';

vi.mock('../src/backend', () => ({ postEvent: vi.fn() }));
const provider = vi.hoisted(() => ({
  getCode: vi.fn(), on: vi.fn(), off: vi.fn(), destroy: vi.fn(), getBlockNumber: vi.fn(), getLogs: vi.fn(), getBlock: vi.fn(),
}));
vi.mock('../src/chain', () => ({ createProvider: () => provider }));
vi.mock('../src/config', () => ({
  EVENT_DELIVERY_ATTEMPTS: 3, EVENT_RETRY_BASE_MS: 1, REPLAY_CHUNK_BLOCKS: 10,
  loadConfig: () => ({
    backendUrl: 'http://backend', rpcUrl: 'http://rpc', contractAddress: '0x1111111111111111111111111111111111111111',
    eventsFromBlock: 0,
  }),
}));
afterEach(() => { vi.restoreAllMocks(); vi.resetAllMocks(); });

const OCCURRED_AT = new Date('2026-07-26T08:00:00Z');
const blockTime = async (): Promise<Date> => OCCURRED_AT;

describe('Event forwarding', () => {
  it('subscribes to all four topics and releases the provider on shutdown', async () => {
    provider.getCode.mockResolvedValue('0x6000');
    provider.getBlockNumber.mockResolvedValue(5);
    provider.getLogs.mockResolvedValue([]);
    vi.spyOn(console, 'log').mockImplementation(() => undefined);
    const stop = await startListener();
    expect(provider.on).toHaveBeenCalledWith(expect.objectContaining({
      address: ADDRESS, topics: [[expect.any(String), expect.any(String), expect.any(String), expect.any(String)]],
    }), expect.any(Function));
    await stop();
    expect(provider.off).toHaveBeenCalledOnce();
    expect(provider.destroy).toHaveBeenCalledOnce();
  });

  it('replays past events in chunks and in chain order, so a setup payment reaches the backend', async () => {
    const first = { ...eventLog('TrancheReleased', ['ATH-0355', 0, 600n, ADDRESS]), blockNumber: 3 };
    const second = { ...eventLog('PaymentHeld', ['ATH-0287', 0, 'Thresholds not met']), blockNumber: 14 };
    provider.getLogs.mockImplementation(async ({ fromBlock }: { fromBlock: number }) => (fromBlock === 0 ? [first] : [second]));
    const forwarded: number[] = [];
    const count = await replayPastEvents(provider, { address: ADDRESS }, { from: 0, to: 15 },
      async log => { forwarded.push(log.blockNumber); });
    expect(count).toBe(2);
    expect(forwarded).toEqual([3, 14]);
    expect(provider.getLogs.mock.calls.map(([filter]) => [filter.fromBlock, filter.toBlock])).toEqual([[0, 9], [10, 15]]);
  });

  it('replays the history the chain had before the listener started', async () => {
    provider.getCode.mockResolvedValue('0x6000');
    provider.getBlockNumber.mockResolvedValue(4);
    provider.getLogs.mockResolvedValue([eventLog('TrancheReleased', ['ATH-0355', 0, 600n, ADDRESS])]);
    provider.getBlock.mockResolvedValue({ timestamp: OCCURRED_AT.getTime() / 1000 });
    vi.mocked(postEvent).mockResolvedValue('posted');
    vi.spyOn(console, 'log').mockImplementation(() => undefined);
    const stop = await startListener();
    expect(postEvent).toHaveBeenCalledOnce();
    await stop();
  });

  it('closes the provider if listener startup cannot reach the RPC', async () => {
    provider.getCode.mockRejectedValue(new Error('Connection refused'));
    await expect(startListener()).rejects.toThrow('Cannot start event listener');
    expect(provider.destroy).toHaveBeenCalledOnce();
  });

  it.each([
    ['TrancheReleased', ['roof', 0, 600n, ADDRESS]],
    ['PaymentHeld', ['roof', 0, 'Thresholds not met']],
    ['ForceMajeureApplied', ['roof', 240n, 680n]],
    ['UnreleasedReclaimed', ['roof', ADDRESS, 1000n]],
  ] as const)('forwards %s to the backend with its block time', async (name, args) => {
    vi.mocked(postEvent).mockResolvedValue('posted');
    await forwardEvent('http://backend', eventLog(name, args), blockTime, new Set());
    expect(postEvent).toHaveBeenCalledWith('http://backend', expect.objectContaining({
      event: name, roofId: 'roof', blockNumber: 42, logIndex: 0,
    }), OCCURRED_AT);
  });

  it('posts a log once even when the provider hands it over again', async () => {
    vi.mocked(postEvent).mockResolvedValue('posted');
    const seen = new Set<string>();
    const log = eventLog('PaymentHeld', ['roof', 0, 'Held']);
    await forwardEvent('http://backend', log, blockTime, seen);
    await forwardEvent('http://backend', log, blockTime, seen);
    expect(postEvent).toHaveBeenCalledOnce();
  });

  it('keeps every event of one transaction: they differ by log index', async () => {
    vi.mocked(postEvent).mockResolvedValue('posted');
    const seen = new Set<string>();
    await forwardEvent('http://backend', eventLog('ForceMajeureApplied', ['roof', 240n, 680n], 0), blockTime, seen);
    await forwardEvent('http://backend', eventLog('PaymentHeld', ['roof', 1, 'Suspended'], 1), blockTime, seen);
    expect(postEvent).toHaveBeenCalledTimes(2);
  });

  it('retries until the backend is back', async () => {
    vi.mocked(postEvent).mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce('posted');
    await forwardEvent('http://backend', eventLog('PaymentHeld', ['roof', 0, 'Held']), blockTime, new Set());
    expect(postEvent).toHaveBeenCalledTimes(2);
  });

  it('gives up after the last attempt, logs the event and allows a later replay', async () => {
    vi.mocked(postEvent).mockRejectedValue(new Error('Backend offline'));
    const output = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const seen = new Set<string>();
    await expect(forwardEvent('http://backend', eventLog('PaymentHeld', ['roof', 0, 'Held']), blockTime, seen))
      .resolves.toBeUndefined();
    expect(postEvent).toHaveBeenCalledTimes(3);
    expect(output).toHaveBeenCalledOnce();
    expect(seen.size).toBe(0);
  });

  it('returns the first successful attempt', async () => {
    const send = vi.fn().mockRejectedValueOnce(new Error('x')).mockResolvedValue('ok');
    expect(await withRetry(send, 3, 1)).toBe('ok');
    expect(send).toHaveBeenCalledTimes(2);
  });
});
