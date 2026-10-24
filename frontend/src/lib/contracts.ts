import type {
  ContractEvent,
  ContractEventName,
  ContractStatus,
  ContractThresholds,
  TrancheName,
  TrancheState,
} from '../api/types'
import { ORIGINAL_ROUND, roundRoofId } from '@shared/demo-round'
import type { ChainSnapshot } from '../chain/contract'

export const TRANCHE_DETAILS: { name: TrancheName; label: string; description: string }[] = [
  {
    name: 'QUALITY',
    label: 'Quality',
    description:
      'Released when the after-coating measurement meets the fixed cooling and coverage thresholds.',
  },
  {
    name: 'DURABILITY',
    label: 'Durability',
    description: 'Released 180 days after the quality payment if the cooling still holds.',
  },
  {
    name: 'FORCE_MAJEURE_RESERVE',
    label: 'Force majeure reserve',
    description: 'Paid to the contractor when a storm makes the durability recheck impossible.',
  },
]
export const TRANCHE_STATUS: Record<TrancheState, { label: string; color: string; icon: string }> =
  {
    released: { label: 'Released', color: 'teal', icon: '✓' },
    held: { label: 'Held', color: 'orange', icon: '!' },
    pending: { label: 'Pending', color: 'gray', icon: '·' },
  }
/** The reason comes from schema/thresholds.json through the backend; none is made up here. */
export function thresholdReason(city: string, thresholds: ContractThresholds): string {
  const rationale =
    thresholds.rationale ?? `No rationale is recorded for ${city}; it uses the default requirement.`
  if (!thresholds.winter_penalty_check) return rationale
  return (
    `${rationale} ${city} also has a real heating season, so its verifications carry a ` +
    'winter-penalty note, for information only.'
  )
}

const WEI_PER_TOKEN = 10n ** 18n
const CELSIUS_TO_X10 = 10

/** Wei arrives as a decimal string, or null when no project exists: never BigInt(undefined). */
export function toWei(value: string | null | undefined): bigint | null {
  if (typeof value !== 'string' || !/^\d+$/.test(value)) return null
  return BigInt(value)
}

export function nativeAmount(value: string | bigint | null | undefined): string {
  const wei = typeof value === 'bigint' ? value : toWei(value)
  if (wei === null) return 'Unavailable'
  const whole = wei / WEI_PER_TOKEN
  const fraction = (wei % WEI_PER_TOKEN).toString().padStart(18, '0').replace(/0+$/, '')
  return `${whole}${fraction ? `.${fraction}` : ''} POL`
}

export function releasedWei(contract: ContractStatus): bigint {
  return contract.tranches
    .filter(tranche => tranche.status === 'released')
    .reduce((total, tranche) => total + (toWei(tranche.amount_wei) ?? 0n), 0n)
}

/** Why a tranche is held lives on its latest PaymentHeld event, not on the tranche. */
export function holdReason(events: ContractEvent[], tranche: TrancheName): string | null {
  const held = events.filter(
    event => event.event_name === 'PaymentHeld' && event.tranche === tranche,
  )
  return held.at(-1)?.reason ?? null
}

export const EVENT_LABELS: Record<ContractEventName, string> = {
  TrancheReleased: 'Tranche released',
  PaymentHeld: 'Payment held',
  ForceMajeureApplied: 'Force majeure applied',
  UnreleasedReclaimed: 'Unreleased funds reclaimed',
}

export function describeEvent(event: ContractEvent): string {
  const tranche = event.tranche?.replaceAll('_', ' ').toLowerCase()
  switch (event.event_name) {
    case 'TrancheReleased':
      return `${nativeAmount(event.amount_wei)} paid to the contractor (${tranche}).`
    case 'PaymentHeld':
      return `${tranche}: ${event.reason ?? 'no reason recorded'}.`
    case 'UnreleasedReclaimed':
      return `${nativeAmount(event.amount_wei)} returned to the sponsor; the project is closed.`
    case 'ForceMajeureApplied':
      return `Storm readings exceeded the limits${event.reason ? ` (${event.reason})` : ''}; the reserve is paid and durability suspended.`
  }
}

export function sortedEvents(events: ContractEvent[]): ContractEvent[] {
  return [...events].sort(
    (a, b) =>
      Date.parse(a.occurred_at) - Date.parse(b.occurred_at) || a.block_number - b.block_number,
  )
}

function sameAddress(backend: string | null, chain: string): boolean {
  return backend !== null && backend.toLowerCase() === chain.toLowerCase()
}

/** The backend has a project the chain lacks; in a later round that means it is unfunded. */
export function missingProjectIssue(roofId: string, round: number): string {
  if (round === ORIGINAL_ROUND) return 'This project does not exist on chain.'
  return (
    `Project ${roundRoofId(roofId, round)} does not exist on chain: demo round ${round} is not ` +
    'funded. Run scripts/demo-round.sh.'
  )
}

/** round is the demo round the backend mirrors; its project is keyed "ATH-0142#3". */
export function compareContractData(
  backend: ContractStatus,
  chain: ChainSnapshot,
  round: number = ORIGINAL_ROUND,
): string[] {
  const project = chain.project
  const chainRoofId = roundRoofId(backend.roof_id, round)
  if (!project.exists) return [missingProjectIssue(backend.roof_id, round)]
  const issues: string[] = []
  if (!sameAddress(backend.contract_address, chain.contractAddress))
    issues.push('Contract address differs from the escrow that was read.')
  if (chainRoofId !== project.roofId) issues.push('Roof ID differs.')
  if (!sameAddress(backend.sponsor, project.sponsor)) issues.push('Sponsor address differs.')
  if (!sameAddress(backend.contractor, project.contractor))
    issues.push('Contractor address differs.')
  if (toWei(backend.total_amount_wei) !== project.totalAmount)
    issues.push('Deposited amount differs.')
  const deltaX10 = BigInt(Math.round(backend.thresholds.min_normalized_delta_c * CELSIUS_TO_X10))
  if (deltaX10 !== project.minNormalizedDeltaCx10) issues.push('Fixed cooling threshold differs.')
  if (BigInt(Math.round(backend.thresholds.min_coverage_pct)) !== project.minCoveragePct)
    issues.push('Fixed coverage threshold differs.')
  for (const tranche of TRANCHE_DETAILS) {
    const record = backend.tranches.find(item => item.name === tranche.name)
    const chainReleased = chain.released[tranche.name]
    if (!record) issues.push(`${tranche.label} is missing from the backend response.`)
    else if ((record.status === 'released') !== chainReleased) {
      issues.push(
        `${tranche.label}: backend says ${record.status}; chain says ${chainReleased ? 'released' : 'not released'}.`,
      )
    }
  }
  return issues
}

const EXPLORER_URL = (import.meta.env.VITE_EXPLORER_URL || 'https://amoy.polygonscan.com').replace(
  /\/+$/,
  '',
)

export type ExplorerKind = 'address' | 'tx' | 'block'

/** No hash means the chain has not made this payment yet; never link to a made-up one. */
export function missingLinkLabel(kind: ExplorerKind, value: string | null): string {
  if (kind === 'tx' && !value) return 'Not yet on chain'
  return `Invalid or missing ${kind === 'tx' ? 'transaction hash' : kind}.`
}

export function explorerUrl(kind: ExplorerKind, value: string | null): string | null {
  if (!value) return null
  const valid =
    kind === 'block'
      ? /^\d+$/.test(value)
      : new RegExp(`^0x[0-9a-fA-F]{${kind === 'address' ? 40 : 64}}$`).test(value)
  return valid ? `${EXPLORER_URL}/${kind}/${value}` : null
}
