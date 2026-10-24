import { Group, Paper, SimpleGrid, Stack, Text, Title } from '@mantine/core'
import type { ReactNode } from 'react'
import type { WeatherSeries } from '../../api/types'
import { Metric } from '../Metric'
import { number, temperature } from '../../lib/format'
import { nearestWeather } from '../../lib/verification'
import { DataSourceBadge } from '../DataSourceBadge'

function utc(timestamp: string): string {
  return `${new Date(timestamp).toLocaleString('en-GB', { timeZone: 'UTC' })} UTC`
}

/** Shows the hour nearest the measurement: that is the weather normalization used. */
export function WeatherCard({
  weather,
  measuredAt,
}: {
  weather: WeatherSeries
  measuredAt: string | null
}): ReactNode {
  const record = nearestWeather(weather, measuredAt)
  if (!record) {
    return (
      <Paper withBorder p="lg">
        <Text size="sm" c="dimmed">
          No weather is recorded for the measurement day.
        </Text>
      </Paper>
    )
  }
  return (
    <Paper withBorder p="lg" data-temperature-card="weather">
      <Stack gap="lg">
        <Group justify="space-between">
          <div>
            <Text className="eyebrow">LOCAL CONDITIONS</Text>
            <Title order={3} mt={4}>
              Weather at measurement
            </Title>
          </div>
          <DataSourceBadge source={record.data_source} />
        </Group>
        <SimpleGrid cols={2} spacing="lg">
          <Metric label="Air temperature" value={temperature(record.ambient_c)} />
          <Metric label="Solar radiation" value={`${number(record.radiation_wm2, 0)} W/m²`} />
          <Metric label="Wind speed" value={`${number(record.wind_ms)} m/s`} />
          <Metric label="Peak gust" value={`${number(record.max_gust_ms)} m/s`} />
          <Metric label="Precipitation" value={`${number(record.precipitation_mm)} mm`} />
        </SimpleGrid>
        <Text size="xs" c="dimmed">
          Hour nearest the measurement: {utc(record.timestamp)}, one of {weather.length} hourly
          records that day.
          {record.data_source === 'third_party'
            ? ' Hourly data from Open-Meteo.'
            : ' Demo seed value, not an observation.'}
        </Text>
      </Stack>
    </Paper>
  )
}
