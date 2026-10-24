import { Button, CopyButton, Group, Paper, Stack, Text, Title } from '@mantine/core'
import type { ReactNode } from 'react'
import { shorten } from '../../lib/format'

function EvidenceValue({ label, value }: { label: string; value: string }): ReactNode {
  return (
    <div>
      <Text size="xs" c="dimmed" mb={6}>
        {label}
      </Text>
      <Group justify="space-between" wrap="nowrap">
        <code title={value} className="evidence-value">
          {value ? shorten(value) : 'Not supplied'}
        </code>
        <CopyButton value={value}>
          {({ copied, copy }) => (
            <Button
              size="xs"
              variant="light"
              disabled={!value}
              onClick={copy}
              color={copied ? 'teal' : 'gray'}
              aria-label={`Copy ${label}`}
            >
              {copied ? 'Copied' : 'Copy'}
            </Button>
          )}
        </CopyButton>
      </Group>
    </div>
  )
}

export function EvidenceCard({ hash, signature }: { hash: string; signature: string }): ReactNode {
  return (
    <Paper withBorder p="lg">
      <Stack gap="lg">
        <div>
          <Text className="eyebrow">EVIDENCE TRAIL</Text>
          <Title order={3} mt={4}>
            Trace the result.
          </Title>
        </div>
        <EvidenceValue label="Evidence hash" value={hash} />
        <EvidenceValue label="Device signature" value={signature} />
        <Text size="xs" c="dimmed">
          Files remain off chain. Hashes identify the evidence; displaying a signature does not
          authenticate its device.
        </Text>
      </Stack>
    </Paper>
  )
}
