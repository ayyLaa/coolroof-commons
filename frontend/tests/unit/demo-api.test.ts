import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError, oracle } from '../../src/api/client'
import {
  demoErrorMessage,
  getDemoRound,
  getVerification,
  resetDemo,
  sendMeasurement,
  submitToChain,
} from '../../src/api/demo'
import { DEMO_SCENARIOS } from '../../src/lib/demo'

afterEach(() => vi.restoreAllMocks())
const signal = new AbortController().signal

describe('Demo API boundaries', () => {
  it('sends readings and a measurement phase, never a precomputed delta', async () => {
    const post = vi.spyOn(api, 'post').mockResolvedValue({ measurement_id: 'm1' })
    const readings = [{ timestamp: '2026-07-15T08:00:30Z', surface_temp_c: 46 }]
    await sendMeasurement(DEMO_SCENARIOS[0], 'after', readings, signal)
    expect(post).toHaveBeenCalledWith(
      '/measurements',
      {
        roof_id: 'ATH-0142',
        phase: 'after',
        readings,
        device_id: 'DEV-0391',
        data_source: 'simulated',
      },
      expect.any(Object),
    )
  })
  it('returns the round a reset opened and the current round', async () => {
    vi.spyOn(api, 'post').mockResolvedValue({ round: 4, roof_ids: [], deleted: {}, restored: {} })
    expect(await resetDemo(signal)).toBe(4)
    vi.spyOn(api, 'get').mockResolvedValue({ round: 4 })
    expect(await getDemoRound(signal)).toBe(4)
  })
  it('refuses a reply without a valid round instead of guessing one', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ round: -1 })
    await expect(getDemoRound(signal)).rejects.toThrow('valid demo round')
    vi.spyOn(api, 'post').mockResolvedValue({})
    await expect(resetDemo(signal)).rejects.toThrow('valid demo round')
  })
  it('rejects a verification of an earlier measurement', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ measured_at: '2026-07-15T08:00:00Z' })
    await expect(getVerification('ATH-0142', '2026-07-15T08:00:30Z', signal)).rejects.toThrow(
      'earlier measurement',
    )
  })
  it('submits through the oracle, not the backend', async () => {
    const post = vi.spyOn(oracle, 'post').mockResolvedValue({ tx_hash: `0x${'ab'.repeat(32)}` })
    const backend = vi.spyOn(api, 'post')
    await submitToChain(DEMO_SCENARIOS[2], signal)
    expect(post).toHaveBeenCalledWith(
      '/submit',
      { roof_id: 'ATH-0355', phase: 'durability' },
      expect.any(Object),
    )
    expect(backend).not.toHaveBeenCalled()
  })
  it('refuses an oracle answer without a transaction hash', async () => {
    vi.spyOn(oracle, 'post').mockResolvedValue({ tx_hash: 'pending' })
    await expect(submitToChain(DEMO_SCENARIOS[0], signal)).rejects.toThrow(
      'did not return a transaction hash',
    )
  })
  it('accepts an explicit refusal without a transaction or explorer link', async () => {
    const refusal = {
      status: 'not_submitted',
      tx_hash: null,
      block_number: null,
      explorer_url: null,
      tranche: 'QUALITY',
      reason: 'Not submitted: status is flagged.',
    }
    vi.spyOn(oracle, 'post').mockResolvedValue(refusal)
    expect(await submitToChain(DEMO_SCENARIOS[1], signal)).toEqual(refusal)
  })
  it('rejects a refusal that claims a transaction was sent', async () => {
    vi.spyOn(oracle, 'post').mockResolvedValue({
      status: 'not_submitted',
      tx_hash: `0x${'ab'.repeat(32)}`,
    })
    await expect(submitToChain(DEMO_SCENARIOS[1], signal)).rejects.toThrow('inconsistent refusal')
  })
  it('shows the server message, and says which server is unreachable', () => {
    expect(
      demoErrorMessage(
        new ApiError(409, { code: 'phase_already_settled', message: 'Already settled on chain.' }),
      ),
    ).toBe('Already settled on chain.')
    expect(demoErrorMessage(new TypeError('network'), true)).toContain('Cannot reach the oracle')
    expect(demoErrorMessage(new TypeError('network'))).toContain('Cannot reach the backend')
  })
})
