// Interface settings only. Verification thresholds are not here: they come from the
// repository's schema/thresholds.json, the backend and the contract read the same file.

// The backend's priority_score is a 0-1 composite, not a percentage.
export const PRIORITY_SCORE = { min: 0, max: 1, step: 0.05 } as const
export const ALBEDO_RANGE = { min: 0, max: 1 } as const
export const DEFAULT_BUDGET_EUR = 40_000
// GET /roofs returns at most this many roofs per request; larger cities are paged.
export const ROOF_PAGE_SIZE = 200
export const DEMO_TIMING = {
  stepDelayMs: 600,
  requestTimeoutMs: 15_000,
  submissionTimeoutMs: 120_000,
} as const
// How often the header re-reads which chain the oracle is on, so a switched RPC shows up.
export const NETWORK_REFRESH_MS = 30_000
// The backend's ASSUMED_COATED_ALBEDO, shown in the verification assumptions; the API
// does not report it.
export const ASSUMED_COATED_ALBEDO = 0.75
