import type { TrancheName, TrancheRecord, Verification } from './types'

/** The oracle's POST /submit answer (oracle/src/server.ts). */
interface SubmittedVerification {
  tx_hash: string
  status: 'released' | 'held' | 'force_majeure' | 'confirmed'
  tranche: TrancheName | null
  reason: string | null
  block_number: number
  explorer_url: string
}

interface RefusedVerification {
  status: 'not_submitted'
  tx_hash: null
  block_number: null
  explorer_url: null
  tranche: TrancheName
  reason: string
}

export type OracleSubmission = SubmittedVerification | RefusedVerification

export interface DemoResult {
  roof_id: string
  submission: OracleSubmission
  verification: Verification
  /** The tranche the contract decided on, with its amount, read back from the backend. */
  tranche: TrancheRecord | null
}
