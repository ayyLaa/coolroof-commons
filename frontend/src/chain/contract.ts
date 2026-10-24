import {
  Contract,
  FetchRequest,
  JsonRpcProvider,
  getAddress,
  isAddress,
  isError,
  ZeroAddress,
} from 'ethers'
import type { TrancheName } from '../api/types'

export const AMOY_CHAIN_ID = 80002
// A local Hardhat node (31337) stands in for Amoy until the demo wallet is funded.
function expectedChainId(): number {
  return Number(import.meta.env.VITE_CHAIN_ID || AMOY_CHAIN_ID)
}
export const READ_ABI = [
  'function getProject(string roofId) view returns ((string roofId,address sponsor,address contractor,uint256 totalAmount,int256 minNormalizedDeltaCx10,uint256 minCoveragePct,uint256 createdAt,bool exists,uint256 qualityReleasedAt))',
  'function getTrancheStatus(string roofId,uint8 tranche) view returns (bool)',
  'error ProjectNotFound(string roofId)',
] as const
export const TRANCHE_INDEX: Record<TrancheName, number> = {
  QUALITY: 0,
  DURABILITY: 1,
  FORCE_MAJEURE_RESERVE: 2,
}
const RPC_TIMEOUT_MS = 10_000

export interface ChainProject {
  roofId: string
  sponsor: string
  contractor: string
  totalAmount: bigint
  minNormalizedDeltaCx10: bigint
  minCoveragePct: bigint
  createdAt: bigint
  exists: boolean
  qualityReleasedAt: bigint
}
export interface ChainSnapshot {
  contractAddress: string
  chainId: number
  blockNumber: number
  project: ChainProject
  released: Record<TrancheName, boolean>
}
export interface ChainOptions {
  rpcUrl: string
  contractAddress?: string
}
export class ChainReadError extends Error {}
/** The escrow reverts reads of an unknown roofId instead of returning exists = false. */
export class ProjectNotFoundError extends ChainReadError {
  readonly roofId: string
  constructor(roofId: string) {
    super(`No escrow project ${roofId} exists on chain.`)
    this.roofId = roofId
  }
}

export function configuredChainOptions(): ChainOptions | null {
  const rpcUrl = import.meta.env.VITE_AMOY_RPC_URL?.trim()
  return rpcUrl
    ? { rpcUrl, contractAddress: import.meta.env.VITE_CONTRACT_ADDRESS?.trim() || undefined }
    : null
}

export async function getProject(
  contract: Contract,
  roofId: string,
  blockTag: number,
): Promise<ChainProject> {
  const project: ChainProject = await contract
    .getFunction('getProject')
    .staticCall(roofId, { blockTag })
  return {
    roofId: project.roofId,
    sponsor: project.sponsor,
    contractor: project.contractor,
    totalAmount: project.totalAmount,
    minNormalizedDeltaCx10: project.minNormalizedDeltaCx10,
    minCoveragePct: project.minCoveragePct,
    createdAt: project.createdAt,
    exists: project.exists,
    qualityReleasedAt: project.qualityReleasedAt,
  }
}

export async function getTrancheStatus(
  contract: Contract,
  roofId: string,
  tranche: TrancheName,
  blockTag: number,
): Promise<boolean> {
  return contract
    .getFunction('getTrancheStatus')
    .staticCall(roofId, TRANCHE_INDEX[tranche], { blockTag }) as Promise<boolean>
}

function connection(
  rpcUrl: string,
  address: string,
): { provider: JsonRpcProvider; address: string } {
  let url: URL
  try {
    url = new URL(rpcUrl)
  } catch {
    throw new ChainReadError('The read-only RPC URL is invalid.')
  }
  if (!['http:', 'https:'].includes(url.protocol))
    throw new ChainReadError('The read-only RPC must use HTTP or HTTPS.')
  if (!isAddress(address) || address === ZeroAddress)
    throw new ChainReadError('The escrow address is invalid.')
  const request = new FetchRequest(rpcUrl)
  request.timeout = RPC_TIMEOUT_MS
  return {
    provider: new JsonRpcProvider(request, undefined, { batchMaxCount: 1 }),
    address: getAddress(address),
  }
}

export async function readContractSnapshot(
  roofId: string,
  backendAddress: string | null,
  options: ChainOptions,
): Promise<ChainSnapshot> {
  const { provider, address } = connection(
    options.rpcUrl,
    options.contractAddress || backendAddress || '',
  )
  try {
    const network = await provider.getNetwork()
    const expected = expectedChainId()
    if (network.chainId !== BigInt(expected))
      throw new ChainReadError(
        `The RPC is connected to chain ${network.chainId}, expected ${expected}.`,
      )
    const blockNumber = await provider.getBlockNumber()
    if ((await provider.getCode(address, blockNumber)) === '0x')
      throw new ChainReadError(
        'No escrow contract is deployed at this address. Backend claims could not be verified.',
      )
    const contract = new Contract(address, READ_ABI, provider)
    const [project, quality, durability, reserve] = await Promise.all([
      getProject(contract, roofId, blockNumber),
      getTrancheStatus(contract, roofId, 'QUALITY', blockNumber),
      getTrancheStatus(contract, roofId, 'DURABILITY', blockNumber),
      getTrancheStatus(contract, roofId, 'FORCE_MAJEURE_RESERVE', blockNumber),
    ])
    return {
      contractAddress: address,
      chainId: expected,
      blockNumber,
      project,
      released: { QUALITY: quality, DURABILITY: durability, FORCE_MAJEURE_RESERVE: reserve },
    }
  } catch (error: unknown) {
    if (error instanceof ChainReadError) throw error
    if (isError(error, 'CALL_EXCEPTION') && error.revert?.name === 'ProjectNotFound')
      throw new ProjectNotFoundError(roofId)
    if (isError(error, 'CALL_EXCEPTION'))
      throw new ChainReadError(
        'The escrow read reverted. Check that this project exists and the address uses the CoolRoofEscrow ABI.',
      )
    throw new ChainReadError(
      'Could not read the chain. The RPC may be unreachable, rate-limited or timed out. No chain verification was completed.',
    )
  } finally {
    provider.destroy()
  }
}
