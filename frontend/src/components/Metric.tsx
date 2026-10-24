import { Stack, Text } from '@mantine/core'
import type { ReactNode } from 'react'

export function Metric({
  label,
  value,
  note,
}: {
  label: string
  value: string
  note?: string
}): ReactNode {
  return (
    <Stack gap={3}>
      <Text size="xs" c="dimmed">
        {label}
      </Text>
      <Text className="metric-value">{value}</Text>
      {note && (
        <Text size="xs" c="dimmed">
          {note}
        </Text>
      )}
    </Stack>
  )
}
