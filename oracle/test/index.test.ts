import { beforeEach, describe, expect, it, vi } from 'vitest';
import { submitToChain } from '../src/index';
import { fetchDemoRound, fetchVerification } from '../src/backend';
import { sendVerification } from '../src/chain';
import { VERIFICATION, TX_HASH } from './fixtures';

vi.mock('../src/config', () => ({ loadConfig: () => ({ backendUrl: 'http://backend', rpcUrl: 'http://rpc', contractAddress: 'address' }) }));
vi.mock('../src/backend', () => ({ fetchVerification: vi.fn(), fetchDemoRound: vi.fn() }));
vi.mock('../src/chain', () => ({ sendVerification: vi.fn() }));
beforeEach(() => { vi.resetAllMocks(); vi.mocked(fetchDemoRound).mockResolvedValue(0); });

describe('submitToChain', () => {
  it('fetches, maps, submits and returns the actual receipt result', async () => {
    vi.mocked(fetchVerification).mockResolvedValue(VERIFICATION);
    const result = { transactionHash: TX_HASH, blockNumber: 42, outcome: 'held' as const, events: [] };
    vi.mocked(sendVerification).mockResolvedValue(result);
    expect(await submitToChain('ATH-0142', 'quality')).toEqual(result);
    expect(fetchVerification).toHaveBeenCalledWith('http://backend', 'ATH-0142');
    expect(sendVerification).toHaveBeenCalledWith(expect.any(Object), expect.objectContaining({
      roofId: 'ATH-0142', status: 0, normalizedDeltaCx10: -111n, coveragePct: 94, phase: 0,
    }));
  });

  it('submits the backend weather-window rainfall without a separate lookup', async () => {
    vi.mocked(fetchVerification).mockResolvedValue({ ...VERIFICATION, measurement_phase: 'durability', status: 'insufficient_data', force_majeure: true, weather: { ...VERIFICATION.weather, precipitation_mm: 68 } });
    vi.mocked(sendVerification).mockResolvedValue({ transactionHash: TX_HASH, blockNumber: 42, outcome: 'force_majeure', events: [] });
    await submitToChain('ATH-0142', 'durability');
    expect(sendVerification).toHaveBeenCalledWith(expect.any(Object), expect.objectContaining({
      forceMajeure: true, status: 3, maxGustMsX10: 243n, precipMmX10: 680n,
    }));
  });

  it.each(['flagged', 'insufficient_data'])('does not submit %s even with passing measurements', async status => {
    vi.mocked(fetchVerification).mockResolvedValue({ ...VERIFICATION, status });
    expect(await submitToChain('ATH-0142', 'quality')).toMatchObject({
      outcome: 'not_submitted', transactionHash: null, reason: expect.stringContaining(`status is ${status}`),
    });
    expect(sendVerification).not.toHaveBeenCalled();
  });

  it.each(['quality', 'durability'] as const)('refuses an inconsistent approved storm in %s', async phase => {
    vi.mocked(fetchVerification).mockResolvedValue({ ...VERIFICATION, measurement_phase: phase === 'quality' ? 'after' : 'durability', force_majeure: true });
    expect(await submitToChain('ATH-0142', phase)).toMatchObject({ outcome: 'not_submitted' });
    expect(sendVerification).not.toHaveBeenCalled();
  });

  it('submits to the project of the round, asking the backend which round when none is given', async () => {
    vi.mocked(fetchVerification).mockResolvedValue(VERIFICATION);
    vi.mocked(sendVerification).mockResolvedValue({ transactionHash: TX_HASH, blockNumber: 42, outcome: 'released', events: [] });
    vi.mocked(fetchDemoRound).mockResolvedValue(4);
    await submitToChain('ATH-0142', 'quality');
    expect(fetchVerification).toHaveBeenCalledWith('http://backend', 'ATH-0142');
    expect(sendVerification).toHaveBeenLastCalledWith(expect.any(Object), expect.objectContaining({ roofId: 'ATH-0142#4' }));
    await submitToChain('ATH-0142', 'quality', 2);
    expect(fetchDemoRound).toHaveBeenCalledOnce();
    expect(sendVerification).toHaveBeenLastCalledWith(expect.any(Object), expect.objectContaining({ roofId: 'ATH-0142#2' }));
  });

  it('refuses a roof ID that already carries a round suffix', async () => {
    await expect(submitToChain('ATH-0142#2', 'quality')).rejects.toThrow('Pass the demo round separately');
    expect(sendVerification).not.toHaveBeenCalled();
  });

  it('does not submit a transaction when the backend fails', async () => {
    vi.mocked(fetchVerification).mockRejectedValue(new Error('Backend offline'));
    await expect(submitToChain('ATH-0142', 'quality')).rejects.toThrow('Backend offline');
    expect(sendVerification).not.toHaveBeenCalled();
  });

  it('does not submit malformed verification data', async () => {
    vi.mocked(fetchVerification).mockResolvedValue({ ...VERIFICATION, normalized_delta_c: null });
    await expect(submitToChain('ATH-0142', 'quality')).rejects.toThrow('normalized_delta_c');
    expect(sendVerification).not.toHaveBeenCalled();
  });
});
