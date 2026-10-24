import { Alert, Button, List, Stack, Text } from '@mantine/core'
import type { ReactNode } from 'react'
import { MIXED_SOURCE_TITLE } from '../api/errors'

/** The backend's 409 mixed_data_source: refused on purpose, so it reads as a rule, not a crash. */
export function MixedDataSourceError({
  message,
  retry,
}: {
  message?: string | null
  retry?: () => void
}): ReactNode {
  return (
    <Alert color="gray" title={MIXED_SOURCE_TITLE} data-testid="mixed-data-source-error">
      <Stack gap="sm">
        <Text size="sm">
          One of the two measurements was taken on the roof and the other comes from the simulation.
          A difference between them would mix a real reading with a modelled one, so the backend
          refused to compute it.
        </Text>
        {message && (
          <Text size="sm" c="dimmed">
            Backend: {message}
          </Text>
        )}
        <List size="sm">
          <List.Item>Compare a measured after-reading with a measured before-reading.</List.Item>
          <List.Item>
            Or keep the demo entirely simulated: reset the demo and run the scenario again.
          </List.Item>
        </List>
        <Text size="xs" c="dimmed">
          Nothing was calculated and no payment was attempted.
        </Text>
        {retry && (
          <Button size="xs" variant="light" color="gray" onClick={retry}>
            Retry
          </Button>
        )}
      </Stack>
    </Alert>
  )
}
