import {
  Accordion,
  Badge,
  Group,
  Paper,
  ScrollArea,
  Stack,
  Table,
  Text,
  Title,
  Tooltip,
} from '@mantine/core'
import type { ReactNode } from 'react'
import type { SatelliteCase, SatelliteEvidence } from '../../api/types'
import { number } from '../../lib/format'
import { correctionOf, formatP, instrumentLabel } from '../../lib/evidence'

const COLUMNS = [
  'City',
  'Roof class',
  'Instrument',
  'Pixel',
  'Roof / pixel',
  'n dark / bright',
  'Bright − dark',
  'p raw',
  'p Bonferroni',
  'q FDR',
  'After correction',
]

function InstrumentBadges({ cases }: { cases: SatelliteCase[] }): ReactNode {
  const instruments = [...new Set(cases.map(item => instrumentLabel(item.instrument)))]
  return (
    <Group gap="xs">
      {instruments.map(name => (
        <Tooltip
          key={name}
          label="Satellite land-surface temperature, measured from orbit"
          withArrow
        >
          <Badge variant="light" color="teal" tabIndex={0}>
            Measured, {name}
          </Badge>
        </Tooltip>
      ))}
    </Group>
  )
}

function CorrectionCell({ value }: { value: SatelliteCase }): ReactNode {
  const correction = correctionOf(value)
  if (correction === 'survives')
    return (
      <Badge color="gray" variant="outline">
        Survives correction
      </Badge>
    )
  if (correction === 'none')
    return (
      <Text size="xs" c="dimmed">
        Not significant
      </Text>
    )
  return (
    <Stack gap={2}>
      <Badge color="yellow" variant="light">
        Raw p &lt; 0.05 only
      </Badge>
      <Text size="xs">does not survive multiple-comparison correction</Text>
    </Stack>
  )
}

function CaseRow({ value }: { value: SatelliteCase }): ReactNode {
  const rawOnly = correctionOf(value) === 'raw_only'
  return (
    <Table.Tr
      className={rawOnly ? 'case-raw-only' : undefined}
      data-correction={correctionOf(value)}
    >
      <Table.Td>{value.city}</Table.Td>
      <Table.Td>{value.roof_class}</Table.Td>
      <Table.Td>{instrumentLabel(value.instrument)}</Table.Td>
      <Table.Td>{value.instrument_resolution_m} m</Table.Td>
      <Table.Td>{number(value.roof_to_pixel_area_ratio, 3)}</Table.Td>
      <Table.Td>
        {value.n_low} / {value.n_high}
      </Table.Td>
      <Table.Td>{number(value.delta_c, 2)} °C</Table.Td>
      <Table.Td>{formatP(value.p_value)}</Table.Td>
      <Table.Td>{formatP(value.p_value_bonferroni)}</Table.Td>
      <Table.Td>{formatP(value.q_value_fdr)}</Table.Td>
      <Table.Td>
        <CorrectionCell value={value} />
      </Table.Td>
    </Table.Tr>
  )
}

function Conclusion({ evidence }: { evidence: SatelliteEvidence }): ReactNode {
  const { conclusion } = evidence
  return (
    <Stack gap="sm">
      <Group gap="lg">
        <Text size="sm">
          Tests run: <strong>{evidence.n_tests}</strong>
        </Text>
        <Text size="sm">
          Bonferroni α: <strong>{evidence.bonferroni_alpha}</strong>
        </Text>
        <Text size="sm">
          Raw p &lt; 0.05: <strong>{conclusion.n_significant_raw}</strong>
        </Text>
        <Text size="sm">
          After Bonferroni: <strong>{conclusion.n_significant_bonferroni}</strong>
        </Text>
        <Text size="sm">
          After FDR: <strong>{conclusion.n_significant_fdr}</strong>
        </Text>
      </Group>
      <Text size="sm" c="dimmed">
        {evidence.multiple_comparison_note}
      </Text>
      <Text size="lg" fw={700}>
        {conclusion.verdict}
      </Text>
      <Accordion variant="contained">
        <Accordion.Item value="detail">
          <Accordion.Control>
            <Text size="sm">Full conclusion and untested explanations</Text>
          </Accordion.Control>
          <Accordion.Panel>
            <Text size="sm">{conclusion.text}</Text>
          </Accordion.Panel>
        </Accordion.Item>
      </Accordion>
    </Stack>
  )
}

export function SatelliteCard({ evidence }: { evidence: SatelliteEvidence }): ReactNode {
  return (
    <Paper withBorder p="xl" className="satellite-card" data-temperature-card="satellite">
      <Stack gap="md">
        <Group justify="space-between" align="flex-start">
          <div>
            <Text className="eyebrow">INDEPENDENT EVIDENCE · {evidence.period}</Text>
            <Title order={3}>Can satellites see a cool roof?</Title>
          </div>
          <InstrumentBadges cases={evidence.cases} />
        </Group>
        <Text size="sm" c="dimmed">
          Bright roofs against dark roofs, eight separate tests. A raw p below 0.05 is not a finding
          on its own: with eight tests, about one such result is expected by chance.
        </Text>
        <ScrollArea>
          <Table withTableBorder withColumnBorders miw={1100}>
            <Table.Thead>
              <Table.Tr>
                {COLUMNS.map(label => (
                  <Table.Th key={label}>{label}</Table.Th>
                ))}
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {evidence.cases.map(value => (
                <CaseRow key={value.case_id} value={value} />
              ))}
            </Table.Tbody>
          </Table>
        </ScrollArea>
        <Conclusion evidence={evidence} />
        <div className="resolution-caveat">
          <Text size="sm" fw={600}>
            Resolution caveat
          </Text>
          <Text size="sm">{evidence.resolution_caveat}</Text>
        </div>
      </Stack>
    </Paper>
  )
}
