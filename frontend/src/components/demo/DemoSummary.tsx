import { Anchor, Badge, Group, Paper, Stack, Text, Title } from '@mantine/core'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import type { DemoResult } from '../../api/demo-types'
import { nativeAmount, TRANCHE_DETAILS } from '../../lib/contracts'
import { DataSourceBadge } from '../DataSourceBadge'

function trancheLabel(result: DemoResult): string {
  const name = result.submission.tranche
  return TRANCHE_DETAILS.find(item => item.name === name)?.label ?? name ?? 'No tranche'
}

/** Which tranche the contract paid or held, how much, and the reason it gave. */
export function DemoSummary({ result }: { result: DemoResult }): ReactNode {
  const { submission, verification } = result
  const paid = submission.status === 'released' || submission.status === 'force_majeure'
  const reason = submission.reason ?? verification.reason
  return (
    <Paper
      withBorder
      p="lg"
      className={`demo-summary ${paid ? 'paid' : 'held'}`}
      data-testid="demo-summary"
      data-temperature-card="demo-summary"
    >
      <Group justify="space-between" align="flex-start" wrap="nowrap">
        <Stack gap="xs" style={{ flex: 1, minWidth: 0 }}>
          <Group>
            <Text className="eyebrow">PAYMENT OUTCOME</Text>
            <Badge color={paid ? 'teal' : 'orange'}>
              {paid
                ? 'Payment released'
                : submission.status === 'not_submitted'
                  ? 'Not submitted'
                  : 'Payment held'}
            </Badge>
            <DataSourceBadge source={verification.data_source} />
          </Group>
          <Title order={2}>
            {paid ? nativeAmount(result.tranche?.amount_wei) : '0 POL paid'}
            <Text component="span" fw={400}>
              {' '}
              · {trancheLabel(result)}
            </Text>
          </Title>
          <Text size="md">{reason}</Text>
          {submission.explorer_url && (
            <Group gap="sm">
              <Text size="sm" c="dimmed">
                Transaction in block {submission.block_number}
              </Text>
              <Anchor
                href={submission.explorer_url}
                target="_blank"
                rel="noopener noreferrer"
                size="sm"
              >
                View on explorer ↗
              </Anchor>
            </Group>
          )}
          <Text size="xs" className="demo-muted">
            The measurements and photo are simulated demo data.{' '}
            {submission.status === 'not_submitted'
              ? 'The oracle refused this result before sending any transaction.'
              : 'The escrow contract checked the submitted result before deciding payment.'}
          </Text>
        </Stack>
        <Anchor
          component={Link}
          to={`/contracts/${encodeURIComponent(result.roof_id)}`}
          fw={600}
          style={{ whiteSpace: 'nowrap' }}
        >
          View escrow →
        </Anchor>
      </Group>
    </Paper>
  )
}
