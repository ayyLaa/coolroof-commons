import { Alert, Badge, Button, Group, List, Loader, Paper, Stack, Text, Title } from '@mantine/core'
import type { ReactNode } from 'react'
import type { ChainComparison } from '../../hooks/useChainComparison'
import { ExplorerLink } from './ExplorerLink'

function ComparisonResult({ comparison }: { comparison: ChainComparison }): ReactNode {
  if (comparison.status === 'disabled')
    return (
      <Alert color="gray" title="Chain check not configured">
        <Text size="sm">No independent chain read has been performed.</Text>
        <Text size="xs" mt="xs">
          Set VITE_AMOY_RPC_URL (and VITE_CHAIN_ID for a local chain) to enable the read-only check.
          No wallet is required.
        </Text>
      </Alert>
    )
  if (comparison.status === 'loading')
    return (
      <Group>
        <Loader size="sm" />
        <Text size="sm" c="dimmed">
          Reading project terms and all three release flags from the chain…
        </Text>
      </Group>
    )
  if (comparison.status === 'error')
    return (
      <Alert color="orange" title="Chain check unavailable">
        {comparison.error}
      </Alert>
    )
  if (comparison.status === 'mismatch')
    return (
      <Alert color="red" title="Backend and chain disagree">
        <List size="sm" spacing="xs">
          {comparison.issues.map(issue => (
            <List.Item key={issue}>{issue}</List.Item>
          ))}
        </List>
      </Alert>
    )
  return (
    <Alert color="teal" title="Project terms and release flags match">
      The backend agrees with the independent chain snapshot for the checked fields.
    </Alert>
  )
}

export function ChainComparisonCard({ comparison }: { comparison: ChainComparison }): ReactNode {
  const matched = comparison.status === 'matched'
  return (
    <Paper withBorder p="lg" className="chain-check-card">
      <Stack gap="md">
        <Group justify="space-between">
          <div>
            <Text className="eyebrow">INDEPENDENT READ</Text>
            <Title order={3} mt={5}>
              On-chain cross-check
            </Title>
          </div>
          <Badge
            variant="light"
            color={matched ? 'teal' : comparison.status === 'mismatch' ? 'red' : 'gray'}
          >
            {matched ? 'Checked' : comparison.status === 'mismatch' ? 'Mismatch' : 'Not verified'}
          </Badge>
        </Group>
        <ComparisonResult comparison={comparison} />
        {comparison.snapshot && (
          <Stack gap="xs">
            <Group gap="xs">
              <Text size="xs" c="dimmed">
                Chain snapshot · block
              </Text>
              <ExplorerLink kind="block" value={String(comparison.snapshot.blockNumber)} />
            </Group>
            <Text size="xs" c="dimmed">
              Project {comparison.snapshot.project.roofId || 'not found'} read from{' '}
              <span title={comparison.snapshot.contractAddress}>
                {comparison.snapshot.contractAddress}
              </span>
            </Text>
          </Stack>
        )}
        <Text size="xs" c="dimmed">
          Checks project identity, deposited amount, fixed thresholds and tranche release flags at
          one block. Hold reasons, transaction hashes and event history are backend records, not
          independently checked here.
        </Text>
        {comparison.status !== 'disabled' && (
          <Button
            variant="light"
            size="xs"
            onClick={comparison.refresh}
            loading={comparison.status === 'loading'}
          >
            Refresh chain check
          </Button>
        )}
      </Stack>
    </Paper>
  )
}
