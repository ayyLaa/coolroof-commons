import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { makeError } from 'ethers'
import { ProjectNotFoundError, readContractSnapshot } from '../../src/chain/contract'

const mocks = vi.hoisted(() => ({
  getNetwork: vi.fn(),
  getBlockNumber: vi.fn(),
  getCode: vi.fn(),
  destroy: vi.fn(),
  call: vi.fn(),
}))
vi.mock('ethers', async importOriginal => {
  const actual = await importOriginal<typeof import('ethers')>()
  return {
    ...actual,
    JsonRpcProvider: class {
      getNetwork = mocks.getNetwork
      getBlockNumber = mocks.getBlockNumber
      getCode = mocks.getCode
      destroy = mocks.destroy
    },
    Contract: class {
      getFunction(name: string): { staticCall: (...args: unknown[]) => unknown } {
        return { staticCall: (...args: unknown[]) => mocks.call(name, ...args) }
      }
    },
  }
})
const ADDRESS = `0x${'11'.repeat(20)}`

beforeEach(() => {
  vi.resetAllMocks()
  // Independent of a developer's .env.local, which may point at a local chain.
  vi.stubEnv('VITE_CHAIN_ID', '80002')
  mocks.getNetwork.mockResolvedValue({ chainId: 80002n })
  mocks.getBlockNumber.mockResolvedValue(123)
  mocks.getCode.mockResolvedValue('0x6000')
})
afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllEnvs()
})

describe('Read-only escrow access', () => {
  it('names the missing project when the escrow reverts with ProjectNotFound', async () => {
    mocks.call.mockRejectedValue(
      makeError('execution reverted', 'CALL_EXCEPTION', {
        action: 'call',
        data: null,
        reason: null,
        transaction: { to: ADDRESS, data: '0x' },
        invocation: null,
        revert: { name: 'ProjectNotFound', signature: 'ProjectNotFound(string)', args: [] },
      }),
    )
    const read = readContractSnapshot('ATH-0142#5', ADDRESS, { rpcUrl: 'http://rpc' })
    await expect(read).rejects.toBeInstanceOf(ProjectNotFoundError)
    await expect(read).rejects.toThrow('No escrow project ATH-0142#5 exists on chain.')
  })

  it('pins every project and tranche call to the same block and destroys the provider', async () => {
    mocks.call.mockImplementation(async (name: string, _roof: string, tranche: number | object) =>
      name === 'getProject'
        ? {
            roofId: 'ATH-0142',
            sponsor: ADDRESS,
            contractor: ADDRESS,
            totalAmount: 1n,
            minNormalizedDeltaCx10: -80n,
            minCoveragePct: 85n,
            createdAt: 1n,
            exists: true,
            qualityReleasedAt: 2n,
          }
        : tranche === 0,
    )
    const result = await readContractSnapshot('ATH-0142', ADDRESS, { rpcUrl: 'http://rpc' })
    expect(result.released).toEqual({
      QUALITY: true,
      DURABILITY: false,
      FORCE_MAJEURE_RESERVE: false,
    })
    expect(result.project.qualityReleasedAt).toBe(2n)
    expect(mocks.call).toHaveBeenCalledWith('getProject', 'ATH-0142', { blockTag: 123 })
    for (const tranche of [0, 1, 2])
      expect(mocks.call).toHaveBeenCalledWith('getTrancheStatus', 'ATH-0142', tranche, {
        blockTag: 123,
      })
    expect(mocks.getCode).toHaveBeenCalledWith(ADDRESS, 123)
    expect(mocks.destroy).toHaveBeenCalledOnce()
  })
  it('rejects a wrong network before making contract calls', async () => {
    mocks.getNetwork.mockResolvedValue({ chainId: 1n })
    await expect(
      readContractSnapshot('ATH-0142', ADDRESS, { rpcUrl: 'http://rpc' }),
    ).rejects.toThrow('expected 80002')
    expect(mocks.call).not.toHaveBeenCalled()
    expect(mocks.destroy).toHaveBeenCalledOnce()
  })
  it('reports unavailable RPCs and missing contract code without reporting a match', async () => {
    mocks.getCode.mockResolvedValue('0x')
    await expect(
      readContractSnapshot('ATH-0142', ADDRESS, { rpcUrl: 'http://rpc' }),
    ).rejects.toThrow('No escrow contract')
    mocks.getCode.mockRejectedValue(new Error('timeout'))
    await expect(
      readContractSnapshot('ATH-0142', ADDRESS, { rpcUrl: 'http://rpc' }),
    ).rejects.toThrow('Could not read the chain')
  })
})
