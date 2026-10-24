import { Paper, SimpleGrid, Stack, Text, Title } from '@mantine/core'
import type { ReactNode } from 'react'
import type { ContractThresholds } from '../../api/types'
import { number } from '../../lib/format'

function Term({ label, value }: { label: string; value: string }): ReactNode {
  return (
    <div>
      <Text size="xs" c="dimmed">
        {label}
      </Text>
      <Text className="large-reading">{value}</Text>
    </div>
  )
}

export function ThresholdCard({ thresholds }: { thresholds: ContractThresholds }): ReactNode {
  return (
    <Paper withBorder p="lg" className="threshold-card" data-temperature-card="thresholds">
      <Stack gap="md">
        <div>
          <Text className="eyebrow">FIXED AT PROJECT CREATION</Text>
          <Title order={3} mt={5}>
            The original terms
          </Title>
        </div>
        <SimpleGrid cols={2} spacing="md">
          <Term
            label="Normalized change at most"
            value={`≤ ${thresholds.min_normalized_delta_c.toFixed(1)} °C`}
          />
          <Term
            label="Coating coverage at least"
            value={`≥ ${number(thresholds.min_coverage_pct, 0)}%`}
          />
          <Term
            label="Force majeure gusts above"
            value={`${number(thresholds.force_majeure_gust_ms)} m/s`}
          />
          <Term
            label="Force majeure rain above"
            value={`${number(thresholds.force_majeure_precip_mm)} mm`}
          />
        </SimpleGrid>
        <Text size="sm">
          Durability recheck {thresholds.durability_check_days} days after the quality payment.
        </Text>
        <Text size="xs" c="dimmed">
          The cooling and coverage thresholds were written into the escrow when the sponsor funded
          the project and cannot be changed afterwards, by the sponsor, the contractor or us. The
          contract checks every measurement against them itself. A more negative cooling value means
          a stronger temperature drop.
        </Text>
      </Stack>
    </Paper>
  )
}
