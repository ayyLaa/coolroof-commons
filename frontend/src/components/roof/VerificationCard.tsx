import { Alert, Badge, Group, List, Paper, Progress, Stack, Text, Title } from '@mantine/core'
import type { ReactNode } from 'react'
import type { Verification, VerificationStatus } from '../../api/types'
import { number, temperature } from '../../lib/format'
import { ASSUMED_COATED_ALBEDO } from '../../lib/config'
import { ANOMALY_EXPLANATIONS, UNKNOWN_FLAG, splitReason } from '../../lib/verification'
import { DataSourceBadge } from '../DataSourceBadge'

const STATUS: Record<VerificationStatus, { color: string; label: string }> = {
  approved: { color: 'green', label: 'Approved' },
  flagged: { color: 'yellow', label: 'Flagged' },
  insufficient_data: { color: 'gray', label: 'Insufficient data' },
}

function DeltaComparison({ verification }: { verification: Verification }): ReactNode {
  const { measured_delta_c: measured, normalized_delta_c: normalized, weather } = verification
  const adjustment = normalized - measured
  return (
    <Stack gap="sm">
      <div className="delta-comparison">
        <div className="delta-reading">
          <Text size="xs" c="dimmed">
            Measured change · raw
          </Text>
          <Text className="large-reading">{temperature(measured)}</Text>
        </div>
        <div className="delta-adjustment" aria-label="Normalization adjustment">
          <Text size="xs" c="dimmed">
            normalization
          </Text>
          <Text fw={700}>
            {adjustment > 0 ? '+' : ''}
            {number(adjustment)} °C
          </Text>
        </div>
        <div className="delta-reading normalized">
          <Text size="xs" c="dimmed">
            Normalized change · decides payout
          </Text>
          <Text className="large-reading">{temperature(normalized)}</Text>
        </div>
      </div>
      <Text size="sm" c="dimmed">
        The before and after visits had different weather. Normalization restates both at the same
        reference conditions, so the payout follows the coating rather than the day. Weather at this
        measurement: {temperature(weather.ambient_c)} air, {number(weather.radiation_wm2, 0)} W/m²
        sun, {number(weather.wind_ms)} m/s wind, gusts {number(weather.max_gust_ms)} m/s.
      </Text>
    </Stack>
  )
}

function AnomalyList({ flags }: { flags: string[] }): ReactNode {
  if (!flags.length)
    return (
      <Text size="sm" c="dimmed">
        No anomalies detected.
      </Text>
    )
  return (
    <List size="sm" spacing="sm">
      {flags.map(flag => (
        <List.Item key={flag}>
          <Text size="sm" fw={600}>
            {flag.replaceAll('_', ' ')}
          </Text>
          <Text size="xs" c="dimmed">
            {ANOMALY_EXPLANATIONS[flag] ?? UNKNOWN_FLAG}
          </Text>
        </List.Item>
      ))}
    </List>
  )
}

function WinterNote({ note }: { note: string }): ReactNode {
  return (
    <Paper withBorder p="md" bg="gray.0" data-testid="winter-penalty-info">
      <Text size="sm" fw={600}>
        Winter penalty · information only
      </Text>
      <Text size="sm" mt={5}>
        {note}
      </Text>
      <Text size="xs" c="dimmed" mt={5}>
        This note does not change the verification status or the payout.
      </Text>
    </Paper>
  )
}

function Assumptions(): ReactNode {
  return (
    <div className="verification-assumptions">
      <Text size="sm" fw={600} mb={6}>
        Assumptions
      </Text>
      <List size="xs" spacing={4}>
        <List.Item>
          After coating, albedo is assumed to be {ASSUMED_COATED_ALBEDO} on the coated share of the
          roof only, weighted by measured coverage; no after-coating albedo is measured.
        </List.Item>
        <List.Item>
          Surface temperature is the roof's own temperature, not air temperature.
        </List.Item>
        <List.Item>A cooler roof surface is not a measured CO2 reduction.</List.Item>
      </List>
    </div>
  )
}

export function VerificationCard({ verification }: { verification: Verification }): ReactNode {
  const status = STATUS[verification.status]
  const { decision, note } = splitReason(verification.reason)
  return (
    <Paper withBorder p="xl" data-temperature-card="verification">
      <Stack gap="lg">
        <Group justify="space-between">
          <div>
            <Text className="eyebrow">OUTCOME VERIFICATION</Text>
            <Title order={3} mt={4}>
              What changed on this roof?
            </Title>
          </div>
          <Group gap="xs">
            <DataSourceBadge source={verification.data_source} />
            <Badge color={status.color} variant="light">
              {status.label}
            </Badge>
          </Group>
        </Group>
        {verification.force_majeure && (
          <Alert color="orange" title="Force majeure">
            Storm conditions made this measurement unreliable. The escrow pays its reserve and
            suspends the durability tranche; it does not treat the reading as a failed coating.
          </Alert>
        )}
        <DeltaComparison verification={verification} />
        <div>
          <Group justify="space-between" mb={8}>
            <Text size="sm" fw={600}>
              Coating coverage
            </Text>
            <Text size="sm">{number(verification.coverage_pct, 1)}%</Text>
          </Group>
          <Progress
            aria-label="Coating coverage"
            value={verification.coverage_pct}
            color={status.color}
            size="lg"
          />
        </div>
        <AnomalyList flags={verification.anomaly_flags} />
        <Text size="sm">{decision}</Text>
        {note && <WinterNote note={note} />}
        <Assumptions />
      </Stack>
    </Paper>
  )
}
