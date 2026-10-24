import { Badge, Group, Stack, Text } from '@mantine/core'
import type { ReactNode } from 'react'
import type { DemoScenario } from '../../lib/demo-scenarios'
import { DEMO_SCENARIOS } from '../../lib/demo'

export function ScenarioButtons({
  selectedId,
  disabled,
  completed,
  onStart,
}: {
  selectedId?: string
  disabled: boolean
  completed: string[]
  onStart: (scenario: DemoScenario) => void
}): ReactNode {
  return (
    <Stack gap="md">
      {DEMO_SCENARIOS.map((scenario, index) => (
        <button
          key={scenario.id}
          className={`scenario-button ${scenario.tone} ${selectedId === scenario.id ? 'selected' : ''}`}
          aria-label={`${scenario.title} (${scenario.roof_id})`}
          aria-pressed={selectedId === scenario.id}
          disabled={disabled || completed.includes(scenario.roof_id)}
          onClick={() => onStart(scenario)}
        >
          <Group justify="space-between">
            <Text size="sm" fw={700}>
              {String(index + 1).padStart(2, '0')} / {scenario.roof_id}
            </Text>
            {completed.includes(scenario.roof_id) ? (
              <Badge color="teal" variant="light">
                Complete
              </Badge>
            ) : (
              <span className="scenario-arrow" aria-hidden="true">
                ↗
              </span>
            )}
          </Group>
          <Text className="scenario-title">{scenario.title}</Text>
          <Text className="demo-muted" size="sm">
            {scenario.description}
          </Text>
        </button>
      ))}
    </Stack>
  )
}
