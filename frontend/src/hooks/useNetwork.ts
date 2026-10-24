import { useEffect, useState } from 'react'
import { getOracleHealth } from '../api/oracle'
import type { OracleHealth } from '../api/types'
import { NETWORK_REFRESH_MS } from '../lib/config'
import { describeError } from './useApiResource'

export interface NetworkState {
  health: OracleHealth | null
  error: string | null
}

/** Which chain the oracle is on, re-read every NETWORK_REFRESH_MS. */
export function useNetwork(): NetworkState {
  const [state, setState] = useState<NetworkState>({ health: null, error: null })
  useEffect(() => {
    const controller = new AbortController()
    const read = (): void => {
      getOracleHealth(controller.signal)
        .then(health => setState({ health, error: null }))
        .catch((error: unknown) => {
          if (!controller.signal.aborted)
            setState({ health: null, error: `Oracle unreachable. ${describeError(error)}` })
        })
    }
    read()
    const timer = setInterval(read, NETWORK_REFRESH_MS)
    return () => {
      clearInterval(timer)
      controller.abort()
    }
  }, [])
  return state
}
