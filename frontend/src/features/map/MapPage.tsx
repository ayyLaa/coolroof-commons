import {
  Alert,
  Badge,
  Group,
  NumberInput,
  Paper,
  Select,
  Slider,
  Stack,
  Text,
  Title,
} from '@mantine/core'
import type { ReactNode } from 'react'
import { useRoofMap } from '../../hooks/useRoofMap'
import { RoofMap } from '../../components/map/RoofMap'
import { RoofList, RoofSummary } from '../../components/map/RoofSummary'
import { ResourcePanel } from '../../components/ResourcePanel'
import { euro, number } from '../../lib/format'
import { PRIORITY_SCORE } from '../../lib/config'
import { ClimateComparisonCard } from '../../components/ClimateComparisonCard'
import { MixedDataSourceError } from '../../components/MixedDataSourceError'

type RoofMapState = ReturnType<typeof useRoofMap>

function MapHeader({ map }: { map: RoofMapState }): ReactNode {
  return (
    <Group justify="space-between" align="flex-start">
      <div>
        <Text className="eyebrow">{map.city.name.toUpperCase()} · URBAN COOLING</Text>
        <Title order={1} mt={5}>
          Find the roofs that matter.
        </Title>
        <Text c="dimmed" size="sm" mt={6}>
          Explore heat exposure. Direct investment where it can make a difference.
        </Text>
      </div>
      <Select
        label="City"
        aria-label="Map city"
        value={map.city.id}
        allowDeselect={false}
        data={map.cities.map(city => ({ value: city.id, label: city.name }))}
        onChange={value => {
          if (value) map.setCity(value)
        }}
      />
    </Group>
  )
}

function MapFilters({ map }: { map: RoofMapState }): ReactNode {
  const spent = map.chosen.reduce((sum, roof) => sum + roof.estimated_cost_eur, 0)
  const budgetText =
    map.budget === null
      ? 'Enter a budget to highlight roofs.'
      : `${map.chosen.length} roofs · ${euro(spent)} allocated · ${euro(map.budget - spent)} remaining`
  return (
    <Paper withBorder p="lg">
      <div className="map-controls">
        <div>
          <Group justify="space-between" mb="md">
            <Text size="sm" fw={600}>
              Minimum priority score
            </Text>
            <Badge variant="light">
              {number(map.minScore, 2)} / {PRIORITY_SCORE.max}
            </Badge>
          </Group>
          <Slider
            thumbLabel="Minimum priority score"
            value={map.minScore}
            onChange={map.setMinScore}
            min={PRIORITY_SCORE.min}
            max={PRIORITY_SCORE.max}
            step={PRIORITY_SCORE.step}
            label={value => number(value, 2)}
            marks={[
              { value: PRIORITY_SCORE.min, label: 'All roofs' },
              { value: PRIORITY_SCORE.max, label: 'Highest priority' },
            ]}
          />
        </div>
        <div className="budget-control">
          <NumberInput
            label="Intervention budget"
            aria-label="Intervention budget in euros"
            prefix="€ "
            placeholder="Enter budget"
            min={0}
            allowNegative={false}
            allowDecimal={false}
            thousandSeparator=","
            value={map.budget ?? ''}
            onChange={value => map.setBudget(typeof value === 'number' ? value : null)}
          />
          <Text size="xs" c="dimmed" mt={5}>
            {budgetText}
          </Text>
        </div>
      </div>
    </Paper>
  )
}

function ClimateSection({ map }: { map: RoofMapState }): ReactNode {
  const { climate } = map
  if (climate.errorCode === 'mixed_data_source')
    return <MixedDataSourceError message={climate.error} retry={climate.retry} />
  if (map.comparisonAvailable && climate.data)
    return <ClimateComparisonCard comparison={climate.data} />
  if (!climate.error || climate.errorCode === 'not_found') return null
  return (
    <Alert color="gray" title="Climate comparison unavailable">
      Seasonal comparison could not be loaded. No city estimates are being shown.
    </Alert>
  )
}

export default function MapPage(): ReactNode {
  const map = useRoofMap()
  const chosenIds = new Set(map.chosen.map(roof => roof.roof_id))
  const inBudget = map.selected !== null && chosenIds.has(map.selected.roof_id)
  return (
    <Stack gap="lg">
      <MapHeader map={map} />
      <MapFilters map={map} />
      <ResourcePanel resource={map}>
        {() => (
          <>
            <Text size="xs" c="dimmed">
              Showing {map.roofs.length} of {map.totalRoofs} roofs in {map.city.name}.
            </Text>
            {!map.roofs.length && (
              <Alert color="gray">
                No roofs meet this priority filter. Lower the score to broaden your search.
              </Alert>
            )}
            <div className="map-workspace">
              <RoofMap
                key={map.city.id}
                city={map.city}
                roofs={map.roofs}
                chosenIds={chosenIds}
                selected={map.selected}
                onSelect={map.setSelectedId}
              />
              <Stack gap="md">
                <RoofSummary roof={map.selected} inBudget={inBudget} />
                <RoofList
                  roofs={map.roofs}
                  selectedId={map.selected?.roof_id}
                  onSelect={map.setSelectedId}
                />
              </Stack>
            </div>
            <Text size="xs" c="dimmed">
              Budget selection takes the highest scores first and skips roofs that exceed the
              remaining budget. Costs are the API's estimates: roof area times the installed price
              per m².
            </Text>
          </>
        )}
      </ResourcePanel>
      <ClimateSection map={map} />
    </Stack>
  )
}
