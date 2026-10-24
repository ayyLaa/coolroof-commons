import { Alert, Badge, Button, Group, Stack, Switch, Text, Title } from '@mantine/core'
import type { ReactNode } from 'react'
import { useEffect, useRef } from 'react'
import { useDemoWorkflow } from '../../hooks/useDemoWorkflow'
import { ResourcePanel } from '../../components/ResourcePanel'
import { ScenarioButtons } from '../../components/demo/ScenarioButtons'
import { MetricsCard } from '../../components/MetricsCard'
import { DemoFlow } from '../../components/demo/DemoFlow'
import { DemoSummary } from '../../components/demo/DemoSummary'
import { MixedDataSourceError } from '../../components/MixedDataSourceError'

type Workflow = ReturnType<typeof useDemoWorkflow>

function DemoHeader({ demo }: { demo: Workflow }): ReactNode {
  return (
    <Group justify="space-between" align="flex-start">
      <div>
        <Text className="eyebrow">COOLROOF COMMONS · PRESENTATION CONSOLE</Text>
        <Title order={1} mt={6}>
          We pay for cooler roofs.
        </Title>
        <Text className="demo-muted" mt="xs">
          One click. Ten checks. A payment tied to the outcome.
        </Text>
      </div>
      <Stack gap="sm" align="flex-end">
        <Switch
          size="md"
          label="Fast mode"
          description="Skip the 600 ms pauses between steps"
          checked={demo.fastMode}
          onChange={event => demo.setFastMode(event.currentTarget.checked)}
        />
        <Badge color="blue" variant="light">
          Backend · oracle · escrow
        </Badge>
      </Stack>
    </Group>
  )
}

/** The reset opens a new round in the backend only; funding it on chain needs the sponsor's
 * key, which the browser does not have. */
function UnfundedRoundAlert({ round }: { round: number | null }): ReactNode {
  if (round === null) return null
  return (
    <Alert color="orange" title="Chain round not funded" data-testid="unfunded-round">
      <Text size="md">
        The backend is on demo round {round}, but the chain has no projects for it, so a scenario
        cannot be paid. Chain round not funded, run scripts/demo-round.sh: it opens and funds a
        fresh round. Then reload this page.
      </Text>
    </Alert>
  )
}

function DemoError({ demo }: { demo: Workflow }): ReactNode {
  const { state } = demo
  if (state.errorCode === 'mixed_data_source') return <MixedDataSourceError message={state.error} />
  if (!state.error) return null
  return (
    <Alert color="red" title={state.resetting ? 'Reset in progress' : 'Demo stopped'}>
      <Text size="md">{state.error}</Text>
    </Alert>
  )
}

export default function DemoPage(): ReactNode {
  const demo = useDemoWorkflow()
  const { state } = demo
  const summary = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (state.result) summary.current?.scrollIntoView({ block: 'nearest', behavior: 'instant' })
  }, [state.result])
  return (
    <Stack gap="lg" className="demo-page">
      <DemoHeader demo={demo} />
      <div className="demo-workspace">
        <Stack gap="lg">
          <ScenarioButtons
            selectedId={state.scenario?.id}
            disabled={state.running || state.resetting}
            completed={state.completedRoofs}
            onStart={demo.start}
          />
          <div>
            <Button
              fullWidth
              size="md"
              variant="outline"
              color="gray"
              onClick={demo.reset}
              loading={state.resetting}
            >
              Reset backend data
            </Button>
            <Text size="xs" className="demo-muted" mt="xs">
              Restores the backend's demo data and opens a new demo round, without funding it on
              chain. To run the scenarios again, use scripts/demo-round.sh instead.
            </Text>
          </div>
          <ResourcePanel resource={demo.metrics}>
            {metrics => <MetricsCard report={metrics} />}
          </ResourcePanel>
        </Stack>
        <Stack gap="lg">
          <UnfundedRoundAlert round={state.unfundedRound} />
          <DemoError demo={demo} />
          <DemoFlow state={state} />
          {state.result && (
            <div ref={summary}>
              <DemoSummary result={state.result} />
            </div>
          )}
        </Stack>
      </div>
    </Stack>
  )
}
