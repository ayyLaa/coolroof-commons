import {
  AppShell,
  Badge,
  Center,
  Container,
  Group,
  Loader,
  NavLink,
  Paper,
  Stack,
  Text,
} from '@mantine/core'
import { lazy, Suspense } from 'react'
import type { ReactNode } from 'react'
import { Link, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import MapPage from './features/map/MapPage'
import { useSelectedRoof } from './hooks/useSelectedRoof'
import { useNetwork } from './hooks/useNetwork'
import { NetworkBadge } from './components/NetworkBadge'
import { networkLabel } from './lib/network'
import { AccessControl } from './features/access/AccessControl'
const RoofDetailPage = lazy(() => import('./features/roof/RoofDetailPage'))
const ContractPage = lazy(() => import('./features/contract/ContractPage'))
const DemoPage = lazy(() => import('./features/demo/DemoPage'))

export default function App(): ReactNode {
  const { pathname } = useLocation()
  const { roofId } = useSelectedRoof()
  const network = useNetwork()
  // The escrow belongs to a roof: with none picked yet, the link leads to the roof list.
  const escrowLink = roofId ? `/contracts/${encodeURIComponent(roofId)}` : '/'
  return (
    <AppShell header={{ height: 64 }} navbar={{ width: 204, breakpoint: 0 }} padding="xl">
      <AppShell.Header px="xl">
        <Group h="100%" justify="space-between">
          <Group gap="sm">
            <span className="brand-mark">⌂</span>
            <Text fw={700} size="lg">
              CoolRoof <span className="brand-secondary">Commons</span>
            </Text>
          </Group>
          <Group gap="sm">
            <AccessControl />
            <NetworkBadge network={networkLabel(network.health, network.error)} />
            <Text size="xs" c="dimmed">
              CITY PILOTS
            </Text>
            <Badge variant="dot" color="teal">
              Urban cooling atlas
            </Badge>
          </Group>
        </Group>
      </AppShell.Header>
      <AppShell.Navbar p="md">
        <Stack gap="xs">
          <Text className="eyebrow" px="sm" mb="sm" mt="lg">
            WORKSPACE
          </Text>
          <NavLink
            component={Link}
            to="/"
            label="Roof atlas"
            description="Explore & prioritize"
            active={pathname === '/' || pathname.startsWith('/roofs/')}
          />
          <NavLink
            component={Link}
            to={escrowLink}
            label="Escrow status"
            active={pathname.startsWith('/contracts/')}
            description={roofId ? `Payments for ${roofId}` : 'Select a roof first'}
          />
          <NavLink
            component={Link}
            to="/demo"
            label="Demo scenarios"
            description="Inspect the outcomes"
            active={pathname === '/demo'}
          />
        </Stack>
        <Paper p="md" className="sidebar-note">
          <span className="sidebar-symbol">↗</span>
          <Text size="sm" fw={600} mt="sm">
            Cooler roofs.
            <br />
            Shared impact.
          </Text>
          <Text size="xs" c="dimmed" mt="xs">
            Invest in measured outcomes for a more resilient city.
          </Text>
        </Paper>
      </AppShell.Navbar>
      <AppShell.Main>
        <Container fluid px={0}>
          <Suspense
            fallback={
              <Center mih={300}>
                <Loader />
              </Center>
            }
          >
            <Routes>
              <Route path="/" element={<MapPage />} />
              <Route path="/roofs/:id" element={<RoofDetailPage />} />
              <Route path="/contracts/:id" element={<ContractPage />} />
              <Route path="/demo" element={<DemoPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Suspense>
        </Container>
      </AppShell.Main>
    </AppShell>
  )
}
