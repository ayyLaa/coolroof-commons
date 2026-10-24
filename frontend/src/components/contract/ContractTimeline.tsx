import { Group, Paper, Stack, Text, Title } from '@mantine/core'
import type { ReactNode } from 'react'
import type { ContractEvent } from '../../api/types'
import { describeEvent, EVENT_LABELS, sortedEvents } from '../../lib/contracts'
import { ExplorerLink } from './ExplorerLink'

function utc(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? 'Time unavailable'
    : `${date.toLocaleString('en-GB', { timeZone: 'UTC' })} UTC`
}

export function ContractTimeline({ events }: { events: ContractEvent[] }): ReactNode {
  return (
    <Paper withBorder p="xl" data-temperature-card="contract-history">
      <Group justify="space-between">
        <div>
          <Text className="eyebrow">PROJECT HISTORY</Text>
          <Title order={3} mt={5}>
            A record of every decision
          </Title>
        </div>
      </Group>
      <Text size="xs" c="dimmed" mt={6} mb="lg">
        Escrow events relayed by the oracle, in the order they happened on chain.
      </Text>
      {!events.length && (
        <Text size="sm" c="dimmed">
          No events yet. They appear once the oracle relays a contract decision.
        </Text>
      )}
      <ol className="contract-timeline" aria-label="Contract event timeline">
        {sortedEvents(events).map(event => (
          <li key={`${event.tx_hash}-${event.event_name}-${event.tranche}`}>
            <span className="timeline-dot" aria-hidden="true" />
            <Stack gap={4}>
              <Text size="xs" c="dimmed">
                <time dateTime={event.occurred_at}>{utc(event.occurred_at)}</time> · block{' '}
                {event.block_number}
              </Text>
              <Text size="sm" fw={600}>
                {EVENT_LABELS[event.event_name]}
              </Text>
              <Text size="sm" c="dimmed">
                {describeEvent(event)}
              </Text>
              <ExplorerLink kind="tx" value={event.tx_hash} />
            </Stack>
          </li>
        ))}
      </ol>
    </Paper>
  )
}
