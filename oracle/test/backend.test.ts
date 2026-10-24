import axios, { AxiosError } from 'axios';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { fetchDemoRound, fetchVerification, postEvent, toBackendEvent } from '../src/backend';
import { decodeEvent } from '../src/events';
import { ADDRESS, eventLog, TX_HASH, VERIFICATION } from './fixtures';

function httpFailure(status: number): AxiosError {
  const error = new AxiosError('HTTP failure');
  Object.assign(error, { response: { status } });
  return error;
}

afterEach(() => vi.restoreAllMocks());

describe('Backend HTTP adapter', () => {
  it('requests the encoded roof URL and returns the response object', async () => {
    const get = vi.spyOn(axios, 'get').mockResolvedValue({ data: VERIFICATION });
    expect(await fetchVerification('http://backend', 'roof/id')).toEqual(VERIFICATION);
    expect(get).toHaveBeenCalledWith('http://backend/verification/roof%2Fid', { timeout: 10000 });
  });

  it('explains backend connection failures and HTTP errors', async () => {
    const get = vi.spyOn(axios, 'get').mockRejectedValue(new AxiosError('Connection refused', 'ECONNREFUSED'));
    await expect(fetchVerification('http://backend', 'roof')).rejects.toThrow('Cannot reach the backend');
    get.mockRejectedValue(httpFailure(500));
    await expect(fetchVerification('http://backend', 'roof')).rejects.toThrow('HTTP 500');
  });

  const OCCURRED_AT = new Date('2026-07-26T08:00:00Z');

  it('POSTs events in the backend contract shape, with tranche names and wei as strings', async () => {
    const post = vi.spyOn(axios, 'post').mockResolvedValue({ status: 201 });
    const event = decodeEvent(eventLog('TrancheReleased', ['roof/id', 2, 600n, ADDRESS]))!;
    expect(await postEvent('http://backend', event, OCCURRED_AT)).toBe('posted');
    expect(post).toHaveBeenCalledWith('http://backend/contracts/roof%2Fid/events', {
      event_name: 'TrancheReleased', tranche: 'FORCE_MAJEURE_RESERVE', amount_wei: '600', tx_hash: TX_HASH,
      block_number: 42, reason: null, occurred_at: '2026-07-26T08:00:00.000Z', round: 0,
    }, { timeout: 10000 });
  });

  it('strips the round suffix from the roof and sends the round next to it', async () => {
    const post = vi.spyOn(axios, 'post').mockResolvedValue({ status: 201 });
    const event = decodeEvent(eventLog('TrancheReleased', ['ATH-0142#3', 0, 600n, ADDRESS]))!;
    await postEvent('http://backend', event, OCCURRED_AT);
    expect(post).toHaveBeenCalledWith('http://backend/contracts/ATH-0142/events',
      expect.objectContaining({ round: 3 }), { timeout: 10000 });
  });

  it('skips an event from another round quietly instead of logging it as refused', async () => {
    const stale = httpFailure(409);
    Object.assign(stale.response!, { data: { code: 'stale_round', message: 'Event is from demo round 1.' } });
    vi.spyOn(axios, 'post').mockRejectedValue(stale);
    const errors = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    vi.spyOn(console, 'log').mockImplementation(() => undefined);
    const event = decodeEvent(eventLog('PaymentHeld', ['ATH-0287#1', 0, 'Measurement thresholds not met']))!;
    expect(await postEvent('http://backend', event, OCCURRED_AT)).toBe('stale');
    expect(errors).not.toHaveBeenCalled();
  });

  it('reads the current demo round and refuses an invalid one', async () => {
    vi.spyOn(axios, 'get').mockResolvedValue({ data: { round: 5 } });
    expect(await fetchDemoRound('http://backend')).toBe(5);
    vi.spyOn(axios, 'get').mockResolvedValue({ data: { round: -2 } });
    await expect(fetchDemoRound('http://backend')).rejects.toThrow('no valid demo round');
    vi.spyOn(axios, 'get').mockRejectedValue(httpFailure(503));
    await expect(fetchDemoRound('http://backend')).rejects.toThrow('No transaction was sent');
  });

  it('maps held, force majeure and reclaim events', () => {
    const held = toBackendEvent(decodeEvent(eventLog('PaymentHeld', ['roof', 1, 'Durability period not elapsed']))!, OCCURRED_AT);
    expect(held).toMatchObject({
      event_name: 'PaymentHeld', tranche: 'DURABILITY', reason: 'Durability period not elapsed', amount_wei: null,
    });
    const storm = toBackendEvent(decodeEvent(eventLog('ForceMajeureApplied', ['roof', 240n, 680n]))!, OCCURRED_AT);
    expect(storm).toMatchObject({
      event_name: 'ForceMajeureApplied', tranche: null, amount_wei: null, reason: 'gusts 24.0 m/s, 68.0 mm precipitation',
    });
    const reclaim = toBackendEvent(decodeEvent(eventLog('UnreleasedReclaimed', ['roof', ADDRESS, 1000n]))!, OCCURRED_AT);
    expect(reclaim).toMatchObject({ event_name: 'UnreleasedReclaimed', tranche: null, amount_wei: '1000' });
  });

  it('does not retry an event the backend refuses, and logs it for manual replay', async () => {
    vi.spyOn(axios, 'post').mockRejectedValue(httpFailure(422));
    const output = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const event = decodeEvent(eventLog('ForceMajeureApplied', ['roof', 0n, 0n]))!;
    expect(await postEvent('http://backend', event, OCCURRED_AT)).toBe('rejected');
    expect(output).toHaveBeenCalledWith(expect.stringContaining('not retried'), expect.stringContaining('ForceMajeureApplied'));
  });

  it('throws on server errors so the listener retries', async () => {
    vi.spyOn(axios, 'post').mockRejectedValue(httpFailure(500));
    const event = decodeEvent(eventLog('PaymentHeld', ['roof', 0, 'Thresholds not met']))!;
    await expect(postEvent('http://backend', event, OCCURRED_AT)).rejects.toThrow('Cannot deliver');
  });

  it('passes the backend error message through for the demo screen', async () => {
    const error = new AxiosError('HTTP failure');
    Object.assign(error, { response: { status: 409, data: { code: 'missing_measurement', message: 'ATH-0142 has no after measurement yet.' } } });
    vi.spyOn(axios, 'get').mockRejectedValue(error);
    await expect(fetchVerification('http://backend', 'ATH-0142'))
      .rejects.toThrow('HTTP 409): ATH-0142 has no after measurement yet. No transaction was sent.');
  });
});
