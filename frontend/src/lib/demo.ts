import type { DemoResult } from '../api/demo-types'
import type { DataSource } from '../api/types'
import type { DemoScenario } from './demo-scenarios'

export { DEMO_SCENARIOS } from './demo-scenarios'
// Coverage comes before normalization: the backend weights the coated albedo by it.
export const DEMO_LABELS = [
  'Sending before measurement',
  'Sending follow-up measurement',
  'Analyzing coverage',
  'Fetching weather',
  'Applying normalization',
  'Checking anomalies',
  'Checking force majeure',
  'Signing evidence',
  'Submitting to contract',
  'Reading the contract decision',
] as const
export const DEMO_SUBMISSION_STEP = DEMO_LABELS.indexOf('Submitting to contract')
export interface DemoStep {
  label: string
  status: 'pending' | 'running' | 'complete' | 'error'
  output: string
  detail: string
  warning: boolean
  data_source?: DataSource
}
export interface DemoState {
  scenario: DemoScenario | null
  steps: DemoStep[]
  running: boolean
  resetting: boolean
  result: DemoResult | null
  error: string | null
  completedRoofs: string[]
  errorCode?: 'mixed_data_source' | null
  /** The round the last reset opened: the backend is on it, the chain has no projects for it. */
  unfundedRound: number | null
}
export function emptyDemoState(): DemoState {
  return {
    scenario: null,
    steps: DEMO_LABELS.map(label => ({
      label,
      status: 'pending',
      output: '',
      detail: '',
      warning: false,
    })),
    running: false,
    resetting: false,
    result: null,
    error: null,
    completedRoofs: [],
    unfundedRound: null,
  }
}
export type DemoAction =
  | { type: 'begin'; scenario: DemoScenario }
  | { type: 'step'; index: number; value: Partial<DemoStep> }
  | { type: 'finish'; result: DemoResult }
  | { type: 'fail'; message: string; errorCode?: 'mixed_data_source' | null }
  | { type: 'reset-start' }
  | { type: 'reset-done'; round: number }
  | { type: 'reset-fail'; message: string; errorCode?: 'mixed_data_source' | null }

export function demoReducer(state: DemoState, action: DemoAction): DemoState {
  switch (action.type) {
    case 'begin':
      return {
        ...emptyDemoState(),
        completedRoofs: state.completedRoofs,
        unfundedRound: state.unfundedRound,
        scenario: action.scenario,
        running: true,
      }
    case 'step':
      return {
        ...state,
        steps: state.steps.map((step, index) =>
          index === action.index ? { ...step, ...action.value } : step,
        ),
      }
    case 'finish':
      return {
        ...state,
        running: false,
        result: action.result,
        completedRoofs: [...state.completedRoofs, action.result.roof_id],
      }
    case 'fail':
      return {
        ...state,
        running: false,
        error: action.message,
        errorCode: action.errorCode,
        steps: state.steps.map(step =>
          step.status === 'running'
            ? { ...step, status: 'error', output: 'Stopped at this step' }
            : step,
        ),
      }
    case 'reset-start':
      return {
        ...state,
        running: false,
        resetting: true,
        error: null,
        errorCode: null,
        steps: state.steps.map(step =>
          step.status === 'running'
            ? { ...step, status: 'error', output: 'Cancelled for reset' }
            : step,
        ),
      }
    case 'reset-done':
      return { ...emptyDemoState(), unfundedRound: action.round }
    case 'reset-fail':
      return { ...state, resetting: false, error: action.message, errorCode: action.errorCode }
  }
}

export function stepPause(milliseconds: number, signal: AbortSignal): Promise<void> {
  if (signal.aborted) return Promise.reject(new DOMException('Aborted', 'AbortError'))
  return new Promise((resolve, reject) => {
    const abort = (): void => {
      clearTimeout(timer)
      reject(new DOMException('Aborted', 'AbortError'))
    }
    const timer = setTimeout(() => {
      signal.removeEventListener('abort', abort)
      resolve()
    }, milliseconds)
    signal.addEventListener('abort', abort, { once: true })
  })
}
