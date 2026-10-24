import { Badge, Button, Divider, Group, Paper, SimpleGrid, Stack, Text, Title } from '@mantine/core'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import type { Roof } from '../../api/types'
import { Metric } from '../Metric'
import { euro, number, temperature } from '../../lib/format'
import { albedoColor } from '../../lib/roofs'
import { DataSourceBadge } from '../DataSourceBadge'

const SCORE_DIGITS = 2

export function RoofSummary({
  roof,
  inBudget,
}: {
  roof: Roof | null
  inBudget: boolean
}): ReactNode {
  if (!roof) {
    return (
      <Paper withBorder p="lg">
        <Text className="eyebrow">ROOF INSPECTOR</Text>
        <Title order={3} mt="sm">
          Start with a rooftop.
        </Title>
        <Text size="sm" c="dimmed" mt="sm">
          Select a building on the map or in the list below to inspect its cooling potential.
        </Text>
      </Paper>
    )
  }
  return (
    <Paper withBorder p="lg" data-temperature-card="roof-summary">
      <Stack gap="md">
        <Group justify="space-between">
          <Text className="eyebrow">ROOF INSPECTOR</Text>
          {inBudget && (
            <Badge color="teal" variant="light" size="sm">
              Within budget
            </Badge>
          )}
        </Group>
        <Title order={2}>{roof.roof_id}</Title>
        <DataSourceBadge source={roof.data_source} />
        <SimpleGrid cols={2} spacing="lg">
          <Metric label="Roof area" value={`${number(roof.area_m2, 0)} m²`} />
          <Metric label="Albedo" value={number(roof.albedo, 2)} />
          <Metric label="Surface temperature" value={temperature(roof.surface_temp_c)} />
          <Metric
            label="Priority score"
            value={`${number(roof.priority_score, SCORE_DIGITS)} / 1`}
          />
        </SimpleGrid>
        <Divider />
        <Group justify="space-between">
          <Text size="sm" c="dimmed">
            Estimated intervention
          </Text>
          <Text fw={600}>{euro(roof.estimated_cost_eur)}</Text>
        </Group>
        <Button component={Link} to={`/roofs/${encodeURIComponent(roof.roof_id)}`} fullWidth>
          View roof details →
        </Button>
      </Stack>
    </Paper>
  )
}

export function RoofList({
  roofs,
  selectedId,
  onSelect,
}: {
  roofs: Roof[]
  selectedId?: string
  onSelect: (id: string) => void
}): ReactNode {
  const sorted = [...roofs].sort((a, b) => b.priority_score - a.priority_score)
  return (
    <Paper withBorder p="md" className="roof-list">
      <Group justify="space-between" mb="sm">
        <Text fw={600} size="sm">
          Priority shortlist
        </Text>
        <Text size="xs" c="dimmed">
          {roofs.length} roofs
        </Text>
      </Group>
      <div className="roof-list-scroll">
        {sorted.map(roof => (
          <button
            key={roof.roof_id}
            className={`roof-list-row ${selectedId === roof.roof_id ? 'active' : ''}`}
            onClick={() => onSelect(roof.roof_id)}
            aria-pressed={selectedId === roof.roof_id}
          >
            <span className="roof-color" style={{ background: albedoColor(roof.albedo) }} />
            <span>
              {roof.roof_id}
              <small>{number(roof.area_m2, 0)} m²</small>
            </span>
            <strong>{number(roof.priority_score, SCORE_DIGITS)}</strong>
          </button>
        ))}
      </div>
    </Paper>
  )
}
