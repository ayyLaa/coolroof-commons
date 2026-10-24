import { Accordion, Badge, Group, List, Paper, SimpleGrid, Stack, Text, Title } from '@mantine/core'
import type { ReactNode } from 'react'
import type { ClimateCity, ClimateComparison, ClimateMethod } from '../api/types'
import { number } from '../lib/format'
import { DataSourceBadge } from './DataSourceBadge'

const METHOD_NAMES: Record<ClimateMethod, string> = {
  demand_weighted: 'Demand-weighted',
  solar_only: 'Solar only',
}

function ranking(cities: ClimateCity[], method: ClimateMethod): string {
  return [...cities]
    .sort((a, b) => b[method].net_benefit_kwh_per_m2 - a[method].net_benefit_kwh_per_m2)
    .map(city => city.city)
    .join(' > ')
}

function CityBalance({
  city,
  method,
  large,
}: {
  city: ClimateCity
  method: ClimateMethod
  large: boolean
}): ReactNode {
  const balance = city[method]
  return (
    <Paper withBorder p="lg">
      <Stack gap="xs">
        <Title order={4}>{city.city}</Title>
        <Text size={large ? '32px' : 'xl'} fw={700} className="climate-net">
          {number(balance.net_benefit_kwh_per_m2)}{' '}
          <Text span size="sm" fw={400}>
            kWh/m² net
          </Text>
        </Text>
        <Group justify="space-between">
          <Text size="sm">Summer cooling benefit</Text>
          <Text size="sm">+{number(balance.cooling_benefit_kwh_per_m2)} kWh/m²</Text>
        </Group>
        <Group justify="space-between">
          <Text size="sm">Winter heating penalty</Text>
          <Text size="sm">−{number(balance.heating_penalty_kwh_per_m2)} kWh/m²</Text>
        </Group>
        {large && (
          <Text size="xs" c="dimmed">
            {city.heat_reference.text}
          </Text>
        )}
      </Stack>
    </Paper>
  )
}

function MethodCities({
  comparison,
  method,
  large,
}: {
  comparison: ClimateComparison
  method: ClimateMethod
  large: boolean
}): ReactNode {
  return (
    <SimpleGrid cols={{ base: 1, sm: 2 }}>
      {comparison.cities.map(city => (
        <CityBalance key={city.city} city={city} method={method} large={large} />
      ))}
    </SimpleGrid>
  )
}

function SecondaryMethod({ comparison }: { comparison: ClimateComparison }): ReactNode {
  const method = comparison.secondary_method
  return (
    <Accordion variant="contained">
      <Accordion.Item value="secondary">
        <Accordion.Control>
          <Text size="sm">
            Secondary method: {METHOD_NAMES[method]}, ranks the cities the other way (
            {ranking(comparison.cities, method)})
          </Text>
        </Accordion.Control>
        <Accordion.Panel>
          <Stack gap="sm">
            <Text size="sm">{comparison.secondary_method_note}</Text>
            <MethodCities comparison={comparison} method={method} large={false} />
          </Stack>
        </Accordion.Panel>
      </Accordion.Item>
    </Accordion>
  )
}

export function ClimateComparisonCard({
  comparison,
}: {
  comparison: ClimateComparison
}): ReactNode {
  const primary = comparison.primary_method
  return (
    <Paper withBorder p="xl" className="climate-card">
      <Stack gap="lg">
        <Group justify="space-between">
          <Title order={3}>Climate comparison</Title>
          <Group>
            <Badge color="gray">Estimate</Badge>
            <DataSourceBadge source={comparison.data_source} />
          </Group>
        </Group>
        <Text size="sm" c="dimmed">
          Sunlight the coating keeps out of the roof, per m², over one summer and one winter.
          Modelled from weather, not measured savings or CO2 reductions.
        </Text>
        <div>
          <Text className="eyebrow">
            PRIMARY METHOD · {METHOD_NAMES[primary].toUpperCase()} ·{' '}
            {ranking(comparison.cities, primary)}
          </Text>
          <Text size="sm" mt="xs" c="dimmed">
            {comparison.method}
          </Text>
        </div>
        <MethodCities comparison={comparison} method={primary} large />
        <Text size="sm">{comparison.conclusion}</Text>
        <SecondaryMethod comparison={comparison} />
        <div>
          <Text fw={600} size="sm">
            Assumptions
          </Text>
          <List size="sm" spacing={4}>
            {comparison.assumptions.map(item => (
              <List.Item key={item}>{item}</List.Item>
            ))}
          </List>
        </div>
        <Text size="sm" c="dimmed">
          {comparison.caveat}
        </Text>
      </Stack>
    </Paper>
  )
}
