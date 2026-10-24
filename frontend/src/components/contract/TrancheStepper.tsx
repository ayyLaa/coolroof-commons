import { Badge, Group, Paper, Stack, Text, Title } from '@mantine/core'
import type { ReactNode } from 'react'
import type { ContractEvent, TrancheRecord } from '../../api/types'
import { holdReason, nativeAmount, TRANCHE_DETAILS, TRANCHE_STATUS } from '../../lib/contracts'
import { ExplorerLink } from './ExplorerLink'

function TrancheBody({
  record,
  reason,
}: {
  record: TrancheRecord
  reason: string | null
}): ReactNode {
  return (
    <Stack gap={8} mt="sm">
      <Text fw={600} size="sm">
        {nativeAmount(record.amount_wei)}
      </Text>
      {record.status === 'released' && (
        <Group gap="xs">
          <Text size="xs" c="dimmed">
            Transaction
          </Text>
          <ExplorerLink kind="tx" value={record.tx_hash} />
        </Group>
      )}
      {record.status === 'held' && (
        <Text size="sm" className="hold-reason">
          {reason ?? 'The contract held this payment; no reason was recorded.'}
        </Text>
      )}
      {record.status === 'pending' && (
        <Text size="xs" c="dimmed">
          Waiting for the verification this tranche depends on.
        </Text>
      )}
    </Stack>
  )
}

export function TrancheStepper({
  tranches,
  events,
}: {
  tranches: TrancheRecord[]
  events: ContractEvent[]
}): ReactNode {
  return (
    <Paper withBorder p="xl">
      <Text className="eyebrow">OUTCOME-BASED PAYMENTS</Text>
      <Title order={3} mt={5} mb="xl">
        Three commitments. Measured release.
      </Title>
      {!tranches.length && (
        <Text size="sm" c="dimmed">
          This roof has no escrow project.
        </Text>
      )}
      <ol className="tranche-stepper" aria-label="Escrow payment tranches">
        {TRANCHE_DETAILS.map(tranche => {
          const record = tranches.find(item => item.name === tranche.name)
          if (!record) return null
          const state = TRANCHE_STATUS[record.status]
          return (
            <li
              key={tranche.name}
              className={`tranche-step ${record.status}`}
              data-testid={`tranche-${tranche.name.toLowerCase()}`}
            >
              <span className="tranche-marker" aria-hidden="true">
                {state.icon}
              </span>
              <div className="tranche-body">
                <Group justify="space-between" align="center">
                  <Text fw={600}>
                    {tranche.label}{' '}
                    <Text component="span" c="dimmed" fw={400}>
                      · {record.pct}%
                    </Text>
                  </Text>
                  <Badge variant="light" color={state.color}>
                    {state.label}
                  </Badge>
                </Group>
                <Text size="xs" c="dimmed" mt={5}>
                  {tranche.description}
                </Text>
                <TrancheBody record={record} reason={holdReason(events, tranche.name)} />
              </div>
            </li>
          )
        })}
      </ol>
    </Paper>
  )
}
