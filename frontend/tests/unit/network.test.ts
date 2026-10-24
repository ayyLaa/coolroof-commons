import { describe, expect, it } from 'vitest'
import type { OracleHealth } from '../../src/api/types'
import { networkLabel } from '../../src/lib/network'

function health(network: OracleHealth['network'], chain_id: number): OracleHealth {
  const wallet = {
    address: `0x${'11'.repeat(20)}`,
    balance: '1',
    round_cost: '0.1',
    rounds_left: 10,
  }
  return {
    ok: true,
    network,
    chain_id,
    contract_address: wallet.address,
    oracle_address: wallet.address,
    balance: '1',
    gas_price_gwei: '30',
    sponsor: wallet,
    oracle: wallet,
  }
}

describe('Network badge', () => {
  it('says which chain the oracle is on, Amoy in a warning colour', () => {
    expect(networkLabel(health('local', 31337), null)).toMatchObject({
      label: 'Local chain · 31337',
      color: 'teal',
    })
    expect(networkLabel(health('amoy', 80002), null)).toMatchObject({
      label: 'Amoy · 80002',
      color: 'orange',
    })
    expect(networkLabel(health('other', 137), null)).toMatchObject({ label: 'Chain 137' })
  })
  it('is never blank, even when the oracle cannot be reached', () => {
    expect(networkLabel(null, 'Oracle unreachable.')).toMatchObject({
      label: 'Chain unknown',
      description: 'Oracle unreachable.',
    })
    expect(networkLabel(null, null).label).toBe('Chain…')
  })
})
