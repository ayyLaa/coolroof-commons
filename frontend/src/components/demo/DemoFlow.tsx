import { Badge, Group, Loader, Paper, Text, Title } from '@mantine/core'
import type { ReactNode } from 'react'
import type { DemoState, DemoStep } from '../../lib/demo'
import { DataSourceBadge } from '../DataSourceBadge'

function StepMarker({ step, index }: { step: DemoStep; index: number }): ReactNode {
  const label =
    step.status === 'running' ? (
      <Loader size={20} />
    ) : step.status === 'complete' ? (
      '✓'
    ) : step.status === 'error' ? (
      '!'
    ) : (
      index + 1
    )
  return (
    <span
      className={`demo-step-marker ${step.status}`}
      aria-label={`Step ${index + 1} ${step.status}`}
    >
      {label}
    </span>
  )
}

function StepRow({ step, index }: { step: DemoStep; index: number }): ReactNode {
  return (
    <li data-status={step.status} data-testid={`demo-step-${index + 1}`}>
      <StepMarker step={step} index={index} />
      <Text className="demo-step-label">{step.label}</Text>
      <div className="demo-step-result">
        <Text className={`demo-step-output ${step.warning ? 'warning-output' : ''}`}>
          {step.output || '—'}
        </Text>
        {step.data_source && <DataSourceBadge source={step.data_source} />}
        {step.detail && <Text className="demo-muted demo-step-detail">{step.detail}</Text>}
      </div>
    </li>
  )
}

function liveStatus(state: DemoState, completed: number): string {
  if (state.running) return `Running ${state.scenario?.title}. ${completed} steps complete.`
  if (state.result) return 'Demo complete.'
  return state.error ? 'Demo stopped.' : 'Choose a scenario to begin.'
}

export function DemoFlow({ state }: { state: DemoState }): ReactNode {
  const completed = state.steps.filter(step => step.status === 'complete').length
  return (
    <Paper withBorder p="xl" className="demo-flow" data-temperature-card="demo-flow">
      <Group justify="space-between" mb="lg">
        <div>
          <Text className="eyebrow">MEASUREMENT → VERIFICATION → PAYMENT</Text>
          <Title order={2} mt={6}>
            {state.scenario?.title ?? 'From measurement to payment.'}
          </Title>
        </div>
        <Badge
          size="lg"
          color={state.running ? 'blue' : completed ? 'teal' : 'gray'}
          variant="light"
        >
          {completed} / {state.steps.length}
        </Badge>
      </Group>
      <ol className="demo-step-list" aria-label="Demo workflow steps">
        {state.steps.map((step, index) => (
          <StepRow key={step.label} step={step} index={index} />
        ))}
      </ol>
      <div className="sr-only" role="status" aria-live="polite">
        {liveStatus(state, completed)}
      </div>
    </Paper>
  )
}
