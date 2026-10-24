import { useEffect, useReducer, useRef, useState } from 'react'
import type { Dispatch, RefObject } from 'react'
import { demoErrorMessage, resetDemo } from '../api/demo'
import type { DemoScenario } from '../lib/demo-scenarios'
import type { MetricsReport } from '../api/types'
import { DEMO_SUBMISSION_STEP, demoReducer, emptyDemoState } from '../lib/demo'
import type { DemoAction, DemoState } from '../lib/demo'
import { runDemoScenario } from '../lib/demo-runner'
import { useMetrics } from './resources'
import type { Resource } from './useApiResource'
import { isMixedDataSourceError } from '../api/errors'

interface Controller {
  active: RefObject<AbortController | null>
  dispatch: Dispatch<DemoAction>
  fast: RefObject<boolean>
  refreshMetrics: () => void
}
interface DemoWorkflow {
  state: DemoState
  metrics: Resource<MetricsReport>
  fastMode: boolean
  setFastMode: (value: boolean) => void
  start: (scenario: DemoScenario) => void
  reset: () => void
}

function startScenario(controller: Controller, scenario: DemoScenario): void {
  if (controller.active.current) return
  const abort = new AbortController()
  controller.active.current = abort
  controller.dispatch({ type: 'begin', scenario })
  let submitting = false
  runDemoScenario(scenario, {
    signal: abort.signal,
    fast: () => controller.fast.current,
    onStep: (index, value) => {
      if (index === DEMO_SUBMISSION_STEP && value.status === 'running') submitting = true
      if (controller.active.current === abort) controller.dispatch({ type: 'step', index, value })
    },
  })
    .then(result => {
      if (controller.active.current === abort) {
        controller.dispatch({ type: 'finish', result })
        controller.refreshMetrics()
      }
    })
    .catch((error: unknown) => {
      if (controller.active.current === abort && !abort.signal.aborted)
        controller.dispatch({
          type: 'fail',
          message: demoErrorMessage(error, submitting),
          errorCode: isMixedDataSourceError(error) ? 'mixed_data_source' : null,
        })
    })
    .finally(() => {
      if (controller.active.current === abort) controller.active.current = null
    })
}

function resetWorkflow(controller: Controller): void {
  controller.active.current?.abort()
  const abort = new AbortController()
  controller.active.current = abort
  controller.dispatch({ type: 'reset-start' })
  resetDemo(abort.signal)
    .then(round => {
      if (controller.active.current === abort) {
        controller.dispatch({ type: 'reset-done', round })
        controller.refreshMetrics()
      }
    })
    .catch((error: unknown) => {
      if (controller.active.current === abort && !abort.signal.aborted)
        controller.dispatch({
          type: 'reset-fail',
          message: `Reset failed. ${demoErrorMessage(error)}`,
          errorCode: isMixedDataSourceError(error) ? 'mixed_data_source' : null,
        })
    })
    .finally(() => {
      if (controller.active.current === abort) controller.active.current = null
    })
}

export function useDemoWorkflow(): DemoWorkflow {
  const [state, dispatch] = useReducer(demoReducer, undefined, emptyDemoState)
  const [fastMode, setFast] = useState(false)
  const active = useRef<AbortController | null>(null)
  const fast = useRef(false)
  const metrics = useMetrics()
  useEffect(
    () => () => {
      active.current?.abort()
      active.current = null
    },
    [],
  )
  const controller: Controller = { active, dispatch, fast, refreshMetrics: metrics.retry }
  return {
    state,
    metrics,
    fastMode,
    setFastMode: value => {
      fast.current = value
      setFast(value)
    },
    start: scenario => {
      if (!state.completedRoofs.includes(scenario.roof_id)) startScenario(controller, scenario)
    },
    reset: () => {
      if (!state.resetting) resetWorkflow(controller)
    },
  }
}
