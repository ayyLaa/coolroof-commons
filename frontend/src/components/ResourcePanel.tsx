import { Alert, Button, Center, Loader, Stack, Text } from '@mantine/core'
import type { ReactNode } from 'react'
import type { Resource } from '../hooks/useApiResource'
import { MixedDataSourceError } from './MixedDataSourceError'
import { NoMeasurementNotice } from './NoMeasurementNotice'

export function ResourcePanel<T>({
  resource,
  children,
}: {
  resource: Resource<T>
  children: (data: T) => ReactNode
}): ReactNode {
  if (resource.loading)
    return (
      <Center mih={140}>
        <Stack align="center" gap="xs">
          <Loader size="sm" />
          <Text size="sm" c="dimmed">
            Loading data…
          </Text>
        </Stack>
      </Center>
    )
  if (resource.errorCode === 'mixed_data_source')
    return <MixedDataSourceError message={resource.error} retry={resource.retry} />
  if (resource.errorCode === 'missing_measurement') return <NoMeasurementNotice />
  if (resource.error)
    return (
      <Alert color="red" title="Data unavailable">
        <Text size="sm">{resource.error}</Text>
        <Button variant="light" color="red" size="xs" mt="sm" onClick={resource.retry}>
          Retry
        </Button>
      </Alert>
    )
  if (resource.data === null) return <Text c="dimmed">No data available.</Text>
  return children(resource.data)
}
