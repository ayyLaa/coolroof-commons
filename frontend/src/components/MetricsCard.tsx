import { Group, Paper, SimpleGrid, Stack, Table, Text, Title } from '@mantine/core'
import type { ReactNode } from 'react'
import type { MetricsReport } from '../api/types'
import { number } from '../lib/format'
import { normalizationSpread, sessionCounts } from '../lib/metrics'
import { DataSourceBadge } from './DataSourceBadge'

const DETECTORS = [
  { key: 'rules', label: 'Rules' },
  { key: 'isolation_forest', label: 'Isolation Forest (ML)' },
  { key: 'combined', label: 'Rules + ML' },
] as const

function percent(value: number): string {
  return `${number(value * 100, 1)}%`
}

function NormalizationSpreadPanel({ report }: { report: MetricsReport }): ReactNode {
  const spread = normalizationSpread(report)
  return (
    <Stack gap="xs">
      <Text className="eyebrow">WHY NORMALIZE</Text>
      <SimpleGrid cols={3}>
        <div>
          <Text size="xs" c="dimmed">
            Raw spread
          </Text>
          <Text className="large-reading">{number(spread.rawRangeC)} °C</Text>
        </div>
        <div>
          <Text size="xs" c="dimmed">
            Normalized spread
          </Text>
          <Text className="large-reading">{number(spread.normalizedRangeC)} °C</Text>
        </div>
        <div>
          <Text size="xs" c="dimmed">
            Narrower by
          </Text>
          <Text className="large-reading">{number(spread.factor)}×</Text>
        </div>
      </SimpleGrid>
      <Text size="xs" c="dimmed">
        The same coating, measured at different hours of a real week of Athens weather, gives raw
        drops that differ by {number(spread.rawRangeC)} °C. After normalization they differ by{' '}
        {number(spread.normalizedRangeC)} °C, so the payout depends on the coating rather than on
        when it was measured.
      </Text>
    </Stack>
  )
}

function DetectionTable({ report }: { report: MetricsReport }): ReactNode {
  const { sessions, anomalies } = sessionCounts(report)
  return (
    <Stack gap="xs">
      <Text className="eyebrow">ANOMALY DETECTION</Text>
      <Table verticalSpacing="xs">
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Detector</Table.Th>
            <Table.Th>Precision</Table.Th>
            <Table.Th>Recall</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {DETECTORS.map(({ key, label }) => (
            <Table.Tr key={key}>
              <Table.Td>{label}</Table.Td>
              <Table.Td>{percent(report.anomaly_detection[key].precision)}</Table.Td>
              <Table.Td>{percent(report.anomaly_detection[key].recall)}</Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      <Text size="xs" c="dimmed">
        {number(sessions, 0)} simulated sessions, {number(anomalies, 0)} of them labelled anomalous.
        Rules catch broken sensors and replays; the Isolation Forest catches implausible cooling the
        rules let through.
      </Text>
    </Stack>
  )
}

export function MetricsCard({ report }: { report: MetricsReport }): ReactNode {
  return (
    <Paper withBorder p="md" className="demo-metrics">
      <Stack gap="md">
        <Group justify="space-between">
          <Title order={3}>Method metrics</Title>
          <DataSourceBadge source={report.data_source} />
        </Group>
        <NormalizationSpreadPanel report={report} />
        <DetectionTable report={report} />
      </Stack>
    </Paper>
  )
}
