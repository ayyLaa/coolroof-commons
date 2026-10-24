import { Badge, Tooltip } from '@mantine/core'
import type { ReactNode } from 'react'
import type { NetworkLabel } from '../lib/network'

export function NetworkBadge({ network }: { network: NetworkLabel }): ReactNode {
  return (
    <Tooltip label={network.description} withArrow>
      <Badge variant="light" color={network.color} tabIndex={0} data-testid="network-badge">
        {network.label}
      </Badge>
    </Tooltip>
  )
}
