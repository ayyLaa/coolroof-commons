import { useEffect, useState } from 'react'
import type { ContractStatus } from '../api/types'
import {
  ChainReadError,
  configuredChainOptions,
  ProjectNotFoundError,
  readContractSnapshot,
} from '../chain/contract'
import type { ChainSnapshot } from '../chain/contract'
import { roundRoofId } from '@shared/demo-round'
import { compareContractData, missingProjectIssue } from '../lib/contracts'

export interface ChainComparison {
  status: 'disabled' | 'loading' | 'matched' | 'mismatch' | 'error'
  snapshot: ChainSnapshot | null
  issues: string[]
  error: string | null
  refresh: () => void
}
type ComparisonState = Omit<ChainComparison, 'refresh'>
const EMPTY: ComparisonState = { status: 'disabled', snapshot: null, issues: [], error: null }

/** The demo round the backend mirrors: null while unknown, with error when it cannot be read. */
export interface RoundLookup {
  round: number | null
  error: string | null
}

export function useChainComparison(backend: ContractStatus, lookup: RoundLookup): ChainComparison {
  const { round, error: roundError } = lookup
  const [attempt, setAttempt] = useState(0)
  const [result, setResult] = useState<{ backend: ContractStatus; value: ComparisonState }>({
    backend,
    value: EMPTY,
  })
  useEffect(() => {
    let active = true
    const options = configuredChainOptions()
    // Without a configured RPC, or for a roof with no project on chain, there is nothing to read.
    if (!options || !backend.contract_address) {
      setResult({ backend, value: EMPTY })
      return
    }
    if (roundError) {
      setResult({ backend, value: { ...EMPTY, status: 'error', error: roundError } })
      return
    }
    setResult({ backend, value: { ...EMPTY, status: 'loading' } })
    // Wait for the round: reading the unsuffixed project in a later round compares the
    // backend with an earlier round's payments.
    if (round === null) return
    readContractSnapshot(roundRoofId(backend.roof_id, round), backend.contract_address, options)
      .then(snapshot => {
        const issues = compareContractData(backend, snapshot, round)
        if (active)
          setResult({
            backend,
            value: {
              snapshot,
              issues,
              error: null,
              status: issues.length ? 'mismatch' : 'matched',
            },
          })
      })
      .catch((error: unknown) => {
        if (active && error instanceof ProjectNotFoundError) {
          const issues = [missingProjectIssue(backend.roof_id, round)]
          setResult({ backend, value: { ...EMPTY, status: 'mismatch', issues } })
        } else if (active)
          setResult({
            backend,
            value: {
              ...EMPTY,
              status: 'error',
              error:
                error instanceof ChainReadError
                  ? error.message
                  : 'The backend response could not be compared with the chain snapshot.',
            },
          })
      })
    return () => {
      active = false
    }
  }, [backend, round, roundError, attempt])
  return {
    ...(result.backend === backend ? result.value : { ...EMPTY, status: 'loading' }),
    refresh: () => setAttempt(value => value + 1),
  }
}
