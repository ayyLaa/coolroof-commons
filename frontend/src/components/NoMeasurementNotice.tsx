import { Alert, Text } from '@mantine/core'
import type { ReactNode } from 'react'

/** The backend's 409 missing_measurement on a roof nobody has measured yet: a gap in the
 * data, not a failure, so it reads as information. Only the demo roofs carry probe
 * sessions; every other roof is a candidate from the satellite survey. */
export function NoMeasurementNotice(): ReactNode {
  return (
    <Alert color="blue" variant="light" title="Not measured yet" data-testid="no-measurement">
      <Text size="sm">
        No field measurement for this roof yet. Verification runs once a before/after pair is
        submitted.
      </Text>
    </Alert>
  )
}
