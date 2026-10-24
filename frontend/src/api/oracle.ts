import { oracle } from './client'
import type { OracleHealth } from './types'

/** The oracle's view of its chain and wallets (GET /health on the oracle, not the backend). */
export function getOracleHealth(signal: AbortSignal): Promise<OracleHealth> {
  return oracle.get<OracleHealth>('/health', { signal })
}
