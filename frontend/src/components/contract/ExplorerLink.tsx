import { Anchor, Code, Text } from '@mantine/core'
import type { ReactNode } from 'react'
import { explorerUrl, missingLinkLabel } from '../../lib/contracts'
import type { ExplorerKind } from '../../lib/contracts'
import { shorten } from '../../lib/format'

export function ExplorerLink({
  kind,
  value,
  full = false,
}: {
  kind: ExplorerKind
  value: string | null
  full?: boolean
}): ReactNode {
  const url = explorerUrl(kind, value)
  if (!url || !value)
    return (
      <Text size="xs" c="dimmed">
        {missingLinkLabel(kind, value)}
      </Text>
    )
  const label = full || kind === 'block' ? value : shorten(value)
  return (
    <Anchor
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      title={value}
      size="sm"
      className="explorer-link"
    >
      <Code>{label}</Code>
      <span aria-hidden="true"> ↗</span>
    </Anchor>
  )
}
