import { Anchor, Badge, Button, Group, Paper, SimpleGrid, Stack, Text, Title } from '@mantine/core'
import type { ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import type { ContractThresholds, RoofDetail } from '../../api/types'
import { RegionalThreshold } from '../../components/roof/RegionalThreshold'
import {
  useContract,
  useRoof,
  useSatelliteEvidence,
  useSeries,
  useVerification,
  useWeather,
} from '../../hooks/resources'
import { useRememberRoof } from '../../hooks/useSelectedRoof'
import { ResourcePanel } from '../../components/ResourcePanel'
import { Metric } from '../../components/Metric'
import { TemperatureCard } from '../../components/roof/TemperatureCard'
import { SatelliteCard } from '../../components/roof/SatelliteCard'
import { VerificationCard } from '../../components/roof/VerificationCard'
import { WeatherCard } from '../../components/roof/WeatherCard'
import { EvidenceCard } from '../../components/roof/EvidenceCard'
import { euro, measurementDay, number, temperature } from '../../lib/format'
import { DataSourceBadge } from '../../components/DataSourceBadge'

const SCORE_DIGITS = 2

function RoofOverview({
  roof,
  thresholds,
}: {
  roof: RoofDetail
  thresholds: ContractThresholds | null
}): ReactNode {
  return (
    <Paper withBorder p="xl" data-temperature-card="roof-overview">
      <Group justify="space-between" mb="lg">
        <div>
          <Text className="eyebrow">
            ROOF PROFILE · {roof.city.toUpperCase()} · {roof.roof_class.toUpperCase()} ROOF
          </Text>
          <Title order={1} mt={4}>
            {roof.roof_id}
          </Title>
        </div>
        <Group gap="sm">
          <DataSourceBadge source={roof.data_source} />
          <Badge variant="light">Priority {number(roof.priority_score, SCORE_DIGITS)}</Badge>
        </Group>
      </Group>
      <SimpleGrid cols={5}>
        <Metric label="Roof area" value={`${number(roof.area_m2, 0)} m²`} />
        <Metric label="Albedo" value={number(roof.albedo, 2)} />
        <Metric label="Surface temperature" value={temperature(roof.surface_temp_c)} />
        <Metric label="Priority score" value={`${number(roof.priority_score, SCORE_DIGITS)} / 1`} />
        <Metric label="Estimated intervention" value={euro(roof.estimated_cost_eur)} />
      </SimpleGrid>
      <RegionalThreshold roof={roof} thresholds={thresholds} />
    </Paper>
  )
}

function ReadingGuide(): ReactNode {
  return (
    <Paper withBorder p="lg">
      <Text className="eyebrow">READING THIS PAGE</Text>
      <Text size="sm" c="dimmed" mt="sm">
        Source badges describe provenance, not certainty. Satellite significance and resolution
        limits are shown explicitly. Verification lists its modelling assumptions.
      </Text>
    </Paper>
  )
}

export default function RoofDetailPage(): ReactNode {
  const { id = '' } = useParams()
  useRememberRoof(id)
  const roof = useRoof(id)
  const contract = useContract(id)
  const series = useSeries(id)
  const satellite = useSatelliteEvidence()
  const verification = useVerification(id)
  const measuredAt = verification.data?.measured_at ?? null
  // An unmeasured roof is said once, in the verification panel; the weather and evidence
  // panels only describe a verified measurement, so they are left out.
  const measured = verification.errorCode !== 'missing_measurement'
  // The weather that matters is the weather on the verified measurement's day.
  const weather = useWeather(id, measurementDay(measuredAt))
  return (
    <Stack gap="lg">
      <Group justify="space-between">
        <Anchor component={Link} to="/" size="sm" c="dimmed">
          ← Back to roof atlas
        </Anchor>
        <Button
          component={Link}
          to={`/contracts/${encodeURIComponent(id)}`}
          variant="light"
          size="xs"
        >
          View escrow status →
        </Button>
      </Group>
      <ResourcePanel resource={roof}>
        {data => <RoofOverview roof={data} thresholds={contract.data?.thresholds ?? null} />}
      </ResourcePanel>
      <ResourcePanel resource={satellite}>
        {data => <SatelliteCard evidence={data} />}
      </ResourcePanel>
      <div className="detail-workspace">
        <Stack gap="lg">
          <ResourcePanel resource={series}>
            {data => <TemperatureCard series={data} />}
          </ResourcePanel>
          <ResourcePanel resource={verification}>
            {data => <VerificationCard verification={data} />}
          </ResourcePanel>
        </Stack>
        <Stack gap="lg">
          {measured && (
            <ResourcePanel resource={weather}>
              {data => <WeatherCard weather={data} measuredAt={measuredAt} />}
            </ResourcePanel>
          )}
          {measured && (
            <ResourcePanel resource={verification}>
              {data => <EvidenceCard hash={data.evidence_hash} signature={data.device_signature} />}
            </ResourcePanel>
          )}
          <ReadingGuide />
        </Stack>
      </div>
    </Stack>
  )
}
