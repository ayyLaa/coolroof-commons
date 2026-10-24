import { Text, Tooltip } from '@mantine/core'
import type { ReactNode } from 'react'
import type { ContractThresholds, Roof } from '../../api/types'
import { thresholdReason } from '../../lib/contracts'
import { number } from '../../lib/format'

export function RegionalThreshold({
  roof,
  thresholds,
}: {
  roof: Roof
  thresholds: ContractThresholds | null
}): ReactNode {
  if (!thresholds)
    return (
      <Text size="sm" mt="md" c="dimmed">
        Thresholds unavailable.
      </Text>
    )
  return (
    <Tooltip multiline w={360} label={thresholdReason(roof.city, thresholds)}>
      <Text size="sm" mt="md" tabIndex={0} data-testid="regional-threshold">
        {roof.city} thresholds: cooling {thresholds.min_normalized_delta_c.toFixed(1)} °C or more,
        coverage {number(thresholds.min_coverage_pct, 0)}% or more ⓘ
      </Text>
    </Tooltip>
  )
}
