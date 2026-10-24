import type { OracleHealth } from '../api/types'

export interface NetworkLabel {
  label: string
  color: string
  description: string
}

/** What the header badge says about the chain the oracle submits to; never left blank, so
 * a demo can not be run against Amoy by mistake without it showing. */
export function networkLabel(health: OracleHealth | null, error: string | null): NetworkLabel {
  if (!health)
    return {
      label: error ? 'Chain unknown' : 'Chain…',
      color: 'gray',
      description: error ?? 'Reading which chain the oracle is connected to.',
    }
  if (health.network === 'local')
    return {
      label: `Local chain · ${health.chain_id}`,
      color: 'teal',
      description: 'Local Hardhat chain: transactions cost nothing.',
    }
  if (health.network === 'amoy')
    return {
      label: `Amoy · ${health.chain_id}`,
      color: 'orange',
      description: 'Polygon Amoy: every transaction spends POL from the demo wallets.',
    }
  return {
    label: `Chain ${health.chain_id}`,
    color: 'red',
    description: 'Neither the local chain nor Amoy: check the oracle configuration.',
  }
}
