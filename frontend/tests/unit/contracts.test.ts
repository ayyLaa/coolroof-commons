import { describe, expect, it } from 'vitest'
import type { ContractEvent, ContractStatus } from '../../src/api/types'
import type { ChainSnapshot } from '../../src/chain/contract'
import {
  compareContractData,
  describeEvent,
  explorerUrl,
  holdReason,
  missingLinkLabel,
  nativeAmount,
  releasedWei,
  sortedEvents,
  thresholdReason,
  toWei,
} from '../../src/lib/contracts'

const TX = `0x${'ab'.repeat(32)}`

function fixtures(): { backend: ContractStatus; chain: ChainSnapshot } {
  const address = `0x${'11'.repeat(20)}`,
    sponsor = `0x${'22'.repeat(20)}`,
    contractor = `0x${'33'.repeat(20)}`
  const backend: ContractStatus = {
    roof_id: 'ATH-0142',
    contract_address: address,
    sponsor,
    contractor,
    total_amount_wei: '1000000000000000000',
    thresholds: {
      min_normalized_delta_c: -8,
      min_coverage_pct: 85,
      force_majeure_gust_ms: 20,
      force_majeure_precip_mm: 50,
      durability_check_days: 180,
      winter_penalty_check: false,
      rationale: null,
    },
    events: [],
    tranches: [
      {
        name: 'QUALITY',
        pct: 60,
        status: 'released',
        amount_wei: '600000000000000000',
        tx_hash: TX,
        released_at: null,
      },
      {
        name: 'DURABILITY',
        pct: 30,
        status: 'held',
        amount_wei: '300000000000000000',
        tx_hash: null,
        released_at: null,
      },
      {
        name: 'FORCE_MAJEURE_RESERVE',
        pct: 10,
        status: 'pending',
        amount_wei: '100000000000000000',
        tx_hash: null,
        released_at: null,
      },
    ],
  }
  const chain: ChainSnapshot = {
    contractAddress: address,
    chainId: 80002,
    blockNumber: 123,
    project: {
      roofId: backend.roof_id,
      sponsor,
      contractor,
      totalAmount: 10n ** 18n,
      minNormalizedDeltaCx10: -80n,
      minCoveragePct: 85n,
      createdAt: 1n,
      exists: true,
      qualityReleasedAt: 2n,
    },
    released: { QUALITY: true, DURABILITY: false, FORCE_MAJEURE_RESERVE: false },
  }
  return { backend, chain }
}

function event(
  name: ContractEvent['event_name'],
  occurredAt: string,
  extra: Partial<ContractEvent> = {},
): ContractEvent {
  return {
    roof_id: 'ATH-0142',
    event_name: name,
    tranche: null,
    amount_wei: null,
    tx_hash: TX,
    block_number: 1,
    reason: null,
    occurred_at: occurredAt,
    round: 0,
    ...extra,
  }
}

describe('Independent contract reconciliation', () => {
  it('matches fixed project terms and release flags, comparing the threshold in tenths', () => {
    const { backend, chain } = fixtures()
    expect(compareContractData(backend, chain)).toEqual([])
  })
  it('detects paid-vs-unpaid discrepancies in either direction', () => {
    const { backend, chain } = fixtures()
    chain.released.QUALITY = false
    chain.released.DURABILITY = true
    expect(compareContractData(backend, chain)).toEqual(
      expect.arrayContaining([
        'Quality: backend says released; chain says not released.',
        'Durability: backend says held; chain says released.',
      ]),
    )
  })
  it('detects threshold, amount, address and identity discrepancies', () => {
    const { backend, chain } = fixtures()
    chain.project.minNormalizedDeltaCx10 = -90n
    chain.project.minCoveragePct = 90n
    chain.project.totalAmount += 1n
    chain.project.roofId = 'OTHER'
    chain.contractAddress = `0x${'44'.repeat(20)}`
    expect(compareContractData(backend, chain)).toHaveLength(5)
  })
  it('treats a backend without a deployment as a mismatch, not a crash', () => {
    const { backend, chain } = fixtures()
    const unconfigured = {
      ...backend,
      contract_address: null,
      sponsor: null,
      contractor: null,
      total_amount_wei: null,
    }
    expect(compareContractData(unconfigured, chain)).toEqual(
      expect.arrayContaining(['Deposited amount differs.']),
    )
  })
  it("compares against the demo round's own project, unsuffixed in round 0", () => {
    const { backend, chain } = fixtures()
    expect(compareContractData(backend, chain, 0)).toEqual([])
    expect(compareContractData(backend, chain, 3)).toEqual(['Roof ID differs.'])
    chain.project.roofId = `${backend.roof_id}#3`
    expect(compareContractData(backend, chain, 3)).toEqual([])
  })
  it('names an unfunded round and how to fund it', () => {
    const { backend, chain } = fixtures()
    chain.project.exists = false
    expect(compareContractData(backend, chain, 3)).toEqual([
      `Project ${backend.roof_id}#3 does not exist on chain: demo round 3 is not funded. ` +
        'Run scripts/demo-round.sh.',
    ])
  })
  it('reports nonexistent projects', () => {
    const { backend, chain } = fixtures()
    chain.project.exists = false
    expect(compareContractData(backend, chain)).toEqual(['This project does not exist on chain.'])
  })
})

describe('Escrow amounts and events', () => {
  it('reads wei strings safely and never calls BigInt on undefined', () => {
    expect(toWei('600000000000000000')).toBe(6n * 10n ** 17n)
    for (const value of [null, undefined, '', 'bad', '-1', '1.5']) expect(toWei(value)).toBeNull()
    expect(nativeAmount(null)).toBe('Unavailable')
  })
  it('sums released tranches only', () => {
    expect(releasedWei(fixtures().backend)).toBe(6n * 10n ** 17n)
  })
  it('takes the hold reason from the latest PaymentHeld of that tranche', () => {
    const events = [
      event('PaymentHeld', '2026-07-01T00:00:00Z', {
        tranche: 'DURABILITY',
        reason: 'Durability period not elapsed',
      }),
      event('PaymentHeld', '2027-01-01T00:00:00Z', {
        tranche: 'DURABILITY',
        reason: 'Durability suspended by force majeure',
      }),
    ]
    expect(holdReason(events, 'DURABILITY')).toBe('Durability suspended by force majeure')
    expect(holdReason(events, 'QUALITY')).toBeNull()
  })
  it('orders the timeline by time, then block', () => {
    const late = event('TrancheReleased', '2026-07-02T00:00:00Z')
    const early = event('PaymentHeld', '2026-07-01T00:00:00Z')
    expect(sortedEvents([late, early])).toEqual([early, late])
  })
  it('shows the storm readings the oracle relayed with force majeure', () => {
    const storm = event('ForceMajeureApplied', '2027-01-21T09:00:00Z', {
      tranche: null,
      reason: 'gusts 24.0 m/s, 68.0 mm precipitation',
    })
    expect(describeEvent(storm)).toBe(
      'Storm readings exceeded the limits (gusts 24.0 m/s, 68.0 mm precipitation); the reserve is paid and durability suspended.',
    )
  })
  it('describes a reclaim as funds returned to the sponsor', () => {
    const reclaim = event('UnreleasedReclaimed', '2027-07-16T00:00:00Z', {
      tranche: null,
      amount_wei: '400000000000000',
    })
    expect(describeEvent(reclaim)).toBe(
      '0.0004 POL returned to the sponsor; the project is closed.',
    )
  })
})

describe('Threshold reason', () => {
  const london = {
    ...fixtures().backend.thresholds,
    min_normalized_delta_c: -6,
    winter_penalty_check: true,
    rationale: 'Scaled from Athens by summer sun.',
  }
  it('shows the recorded rationale, adding the heating-season note only where it applies', () => {
    expect(thresholdReason('London', london)).toBe(
      'Scaled from Athens by summer sun. London also has a real heating season, so its ' +
        'verifications carry a winter-penalty note, for information only.',
    )
    expect(thresholdReason('Athens', { ...london, winter_penalty_check: false })).toBe(
      'Scaled from Athens by summer sun.',
    )
  })
  it('says no rationale is recorded instead of inventing one', () => {
    expect(
      thresholdReason('Lisbon', { ...london, rationale: null, winter_penalty_check: false }),
    ).toBe('No rationale is recorded for Lisbon; it uses the default requirement.')
  })
})

describe('Explorer links', () => {
  it('preserves wei precision when formatting native currency', () => {
    expect(nativeAmount('1000000000000000001')).toBe('1.000000000000000001 POL')
    expect(nativeAmount('0')).toBe('0 POL')
  })
  it('only links valid hashes, addresses and blocks', () => {
    expect(explorerUrl('tx', TX)).toBe(`https://amoy.polygonscan.com/tx/${TX}`)
    expect(explorerUrl('tx', 'javascript:alert(1)')).toBeNull()
    expect(explorerUrl('address', '0x123')).toBeNull()
    expect(explorerUrl('tx', null)).toBeNull()
    expect(explorerUrl('block', '123')).toBe('https://amoy.polygonscan.com/block/123')
  })
  it('says a payment without a hash is not yet on chain instead of linking anywhere', () => {
    expect(missingLinkLabel('tx', null)).toBe('Not yet on chain')
    expect(missingLinkLabel('tx', '0xbad')).toBe('Invalid or missing transaction hash.')
    expect(missingLinkLabel('address', null)).toBe('Invalid or missing address.')
  })
})
