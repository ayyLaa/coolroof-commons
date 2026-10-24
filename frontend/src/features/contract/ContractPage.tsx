import {
  Alert,
  Anchor,
  Badge,
  Button,
  CopyButton,
  Group,
  Paper,
  SimpleGrid,
  Stack,
  Text,
  Title,
} from '@mantine/core'
import type { ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import type { ContractStatus } from '../../api/types'
import { useContract, useDemoRound } from '../../hooks/resources'
import { useChainComparison } from '../../hooks/useChainComparison'
import { useRememberRoof } from '../../hooks/useSelectedRoof'
import { ResourcePanel } from '../../components/ResourcePanel'
import { Metric } from '../../components/Metric'
import { ExplorerLink } from '../../components/contract/ExplorerLink'
import { TrancheStepper } from '../../components/contract/TrancheStepper'
import { ThresholdCard } from '../../components/contract/ThresholdCard'
import { ContractTimeline } from '../../components/contract/ContractTimeline'
import { ChainComparisonCard } from '../../components/contract/ChainComparisonCard'
import { nativeAmount, releasedWei, toWei } from '../../lib/contracts'

function Party({ label, address }: { label: string; address: string | null }): ReactNode {
  return (
    <Group gap="sm">
      <Text size="sm" c="dimmed" w={120}>
        {label}
      </Text>
      {address ? (
        <ExplorerLink kind="address" value={address} full />
      ) : (
        <Text size="sm" c="dimmed">
          Not configured
        </Text>
      )}
      {address && (
        <CopyButton value={address}>
          {({ copied, copy }) => (
            <Button variant="subtle" size="xs" onClick={copy} aria-label={`Copy ${label}`}>
              {copied ? 'Copied' : 'Copy'}
            </Button>
          )}
        </CopyButton>
      )}
    </Group>
  )
}

function ContractHeader({ contract }: { contract: ContractStatus }): ReactNode {
  const total = toWei(contract.total_amount_wei)
  const released = releasedWei(contract)
  const releasedCount = contract.tranches.filter(tranche => tranche.status === 'released').length
  return (
    <Paper withBorder p="xl">
      <Stack gap="lg">
        <Group justify="space-between">
          <div>
            <Text className="eyebrow">OUTCOME ESCROW</Text>
            <Title order={1} mt={5}>
              {contract.roof_id}
            </Title>
          </div>
          <Badge variant="light">
            {releasedCount} / {contract.tranches.length || 3} tranches released
          </Badge>
        </Group>
        <Stack gap={6}>
          <Party label="Escrow contract" address={contract.contract_address} />
          <Party label="Sponsor" address={contract.sponsor} />
          <Party label="Contractor" address={contract.contractor} />
        </Stack>
        <SimpleGrid cols={3}>
          <Metric label="Sponsor deposit" value={nativeAmount(total)} />
          <Metric label="Paid to contractor" value={nativeAmount(released)} />
          <Metric
            label="Still in escrow"
            value={total === null ? 'Unavailable' : nativeAmount(total - released)}
          />
        </SimpleGrid>
      </Stack>
    </Paper>
  )
}

function ContractDashboard({ contract }: { contract: ContractStatus }): ReactNode {
  const round = useDemoRound()
  const chain = useChainComparison(contract, round)
  // A new round may have been funded since the page opened, so a refresh reads both again.
  const comparison = {
    ...chain,
    refresh: () => {
      round.retry()
      chain.refresh()
    },
  }
  if (!contract.tranches.length) {
    return (
      <Alert color="gray" title="No escrow project for this roof">
        Only roofs a sponsor has funded have an escrow. The demo roofs are ATH-0142, ATH-0287 and
        ATH-0355.
      </Alert>
    )
  }
  return (
    <Stack gap="lg">
      <ContractHeader contract={contract} />
      <div className="contract-workspace">
        <Stack gap="lg">
          <TrancheStepper tranches={contract.tranches} events={contract.events} />
          <ContractTimeline events={contract.events} />
        </Stack>
        <Stack gap="lg">
          <ChainComparisonCard comparison={comparison} />
          <ThresholdCard thresholds={contract.thresholds} />
        </Stack>
      </div>
    </Stack>
  )
}

export default function ContractPage(): ReactNode {
  const { id = '' } = useParams()
  useRememberRoof(id)
  const resource = useContract(id)
  return (
    <Stack gap="lg">
      <Group justify="space-between">
        <Anchor component={Link} to={`/roofs/${encodeURIComponent(id)}`} size="sm" c="dimmed">
          ← Back to roof details
        </Anchor>
        <Text size="xs" c="dimmed">
          Funding follows verified outcomes.
        </Text>
      </Group>
      <ResourcePanel resource={resource}>
        {contract => <ContractDashboard contract={contract} />}
      </ResourcePanel>
    </Stack>
  )
}
