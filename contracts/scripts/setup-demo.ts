import { ethers } from 'hardhat';
import type { CoolRoofEscrow } from '../typechain-types';
import { CoolRoofEscrow__factory } from '../typechain-types';
import type { Signer } from 'ethers';
import { APPROVED_STATUS, DEMO_DEPOSIT, DEMO_PROJECTS, DEMO_THRESHOLDS, QUALITY_PAID_AT_SETUP, TRANCHE } from './lib/demo';
import { DEPLOYMENT_PATH, readDeployment, requireAddress, requireDeployedCode, requireSpendAllowed } from './lib/deployment';
import { ORIGINAL_ROUND, parseRound, roundRoofId } from '../shared/demo-round';

const MAX_ERROR_DEPTH = 4;
// The simulated quality visit precedes the January 2027 storm visit.
const DEMO_QUALITY_MEASURED_AT = Math.floor(Date.parse('2026-07-15T08:00:00Z') / 1000);

type DemoProject = typeof DEMO_PROJECTS[number];
/** A demo project as funded in one round: chainRoofId is the escrow's key for it. */
type RoundProject = DemoProject & { chainRoofId: string };

export interface SetupOptions {
  filePath?: string;
  /** The escrow address, when there is no manifest to read it from. */
  address?: string;
  projects?: readonly DemoProject[];
  round?: number;
}

// In-process Hardhat puts the revert data on the error itself; a JSON-RPC node (a local
// `hardhat node`, Amoy) nests it, or only names the custom error in the message.
function isProjectNotFound(escrow: CoolRoofEscrow, error: unknown, depth = 0): boolean {
  if (typeof error !== 'object' || error === null || depth > MAX_ERROR_DEPTH) return false;
  const record = error as Record<string, unknown>;
  if (typeof record.data === 'string' && ethers.isHexString(record.data)
    && escrow.interface.parseError(record.data)?.name === 'ProjectNotFound') return true;
  if (typeof record.message === 'string' && record.message.includes("custom error 'ProjectNotFound(")) return true;
  return ['error', 'info', 'cause'].some(key => isProjectNotFound(escrow, record[key], depth + 1));
}

async function projectExists(escrow: CoolRoofEscrow, roofId: string): Promise<boolean> {
  try {
    await escrow.getProject(roofId);
    return true;
  } catch (error: unknown) {
    if (isProjectNotFound(escrow, error)) return false;
    throw error;
  }
}

async function validateExistingProject(
  escrow: CoolRoofEscrow, roofId: string, sponsor: string, contractor: string, deposit: bigint,
): Promise<boolean> {
  if (!await projectExists(escrow, roofId)) return false;
  const project = await escrow.getProject(roofId);
  if (project.sponsor !== sponsor || project.contractor !== contractor || project.totalAmount !== deposit
    || project.minNormalizedDeltaCx10 !== BigInt(DEMO_THRESHOLDS.minNormalizedDeltaCx10)
    || project.minCoveragePct !== BigInt(DEMO_THRESHOLDS.minCoveragePct)) {
    throw new Error(`Existing project ${roofId} does not match demo terms`);
  }
  return true;
}

async function oracleSigner(escrow: CoolRoofEscrow): Promise<Signer> {
  const oracle = await escrow.oracle();
  const signer = (await ethers.getSigners()).find(account => account.address === oracle);
  if (!signer) throw new Error('Set ORACLE_PRIVATE_KEY to the escrow oracle key; the storm demo needs its quality tranche paid');
  return signer;
}

// Not a measurement: it only moves the storm project to where its demo begins, the
// durability recheck, using the scenario's own passing values.
async function payQualityAtSetup(escrow: CoolRoofEscrow, projects: readonly RoundProject[]): Promise<void> {
  for (const project of projects.filter(demo => QUALITY_PAID_AT_SETUP.includes(demo.roofId))) {
    const roofId = project.chainRoofId;
    if (await escrow.getTrancheStatus(roofId, TRANCHE.QUALITY)) {
      console.log(`Quality already paid: ${roofId}`);
      continue;
    }
    const evidenceHash = ethers.keccak256(ethers.toUtf8Bytes(`${roofId}:setup-quality`));
    const transaction = await escrow.connect(await oracleSigner(escrow)).submitVerification(roofId,
      APPROVED_STATUS, project.normalizedDeltaCx10, project.coveragePct, false, TRANCHE.QUALITY, evidenceHash, '0x', 0, 0, ethers.id(`${roofId}:setup-measurement`), DEMO_QUALITY_MEASURED_AT);
    await transaction.wait();
    console.log(`Paid quality for ${roofId}; transaction ${transaction.hash}`);
  }
}

// On a tight Amoy budget the roofs can be funded one at a time: DEMO_ROOF_IDS=ATH-0142.
export function selectDemoProjects(roofIds: string | undefined): readonly DemoProject[] {
  const ids = (roofIds ?? '').split(',').map(id => id.trim()).filter(Boolean);
  if (!ids.length) return DEMO_PROJECTS;
  const unknown = ids.filter(id => !DEMO_PROJECTS.some(project => project.roofId === id));
  if (unknown.length) throw new Error(`Unknown demo roof IDs: ${unknown.join(', ')}`);
  return DEMO_PROJECTS.filter(project => ids.includes(project.roofId));
}

async function createMissingProjects(
  escrow: CoolRoofEscrow, sponsor: string, contractor: string, projects: readonly RoundProject[],
): Promise<void> {
  const deposit = ethers.parseEther(DEMO_DEPOSIT);
  const existing = await Promise.all(projects.map(project =>
    validateExistingProject(escrow, project.chainRoofId, sponsor, contractor, deposit)));
  const requiredBalance = deposit * BigInt(existing.filter(value => !value).length);
  if (await ethers.provider.getBalance(sponsor) <= requiredBalance) {
    throw new Error('Sponsor needs demo deposits plus native currency for gas');
  }
  for (const [index, project] of projects.entries()) {
    if (existing[index]) { console.log(`Already exists: ${project.chainRoofId}`); continue; }
    const transaction = await escrow.createProject(project.chainRoofId, contractor,
      DEMO_THRESHOLDS.minNormalizedDeltaCx10, DEMO_THRESHOLDS.minCoveragePct, { value: deposit });
    await transaction.wait();
    console.log(`Created ${project.chainRoofId}: ${DEMO_DEPOSIT} native token; transaction ${transaction.hash}`);
  }
}

/** Creates and funds the demo projects of one round; projects that already exist with
 * the demo terms are skipped, so a rerun after a failure costs no second deposit. */
export async function setupDemo(contractorAddress: string, options: SetupOptions = {}): Promise<void> {
  const round = parseRound(options.round ?? ORIGINAL_ROUND);
  await requireSpendAllowed();
  const contractor = requireAddress(contractorAddress, 'CONTRACTOR_ADDRESS');
  const address = options.address === undefined
    ? await readDeployment(options.filePath ?? DEPLOYMENT_PATH) : await requireDeployedCode(options.address);
  const [sponsor] = await ethers.getSigners();
  if (!sponsor) throw new Error('No sponsor account configured; set PRIVATE_KEY');
  if (contractor === address) throw new Error('Contractor cannot be the escrow contract');
  const escrow = CoolRoofEscrow__factory.connect(address, sponsor);
  const projects = (options.projects ?? DEMO_PROJECTS)
    .map(project => ({ ...project, chainRoofId: roundRoofId(project.roofId, round) }));
  await createMissingProjects(escrow, sponsor.address, contractor, projects);
  await payQualityAtSetup(escrow, projects);
}

/** The hardhat setup-demo task and `hardhat run` both end here. */
export async function runSetupDemo(round: number, roofIds: string | undefined): Promise<void> {
  await setupDemo(requireAddress(process.env.CONTRACTOR_ADDRESS, 'CONTRACTOR_ADDRESS'), {
    address: process.env.CONTRACT_ADDRESS || undefined,
    projects: selectDemoProjects(roofIds),
    round,
  });
  console.log(`Demo round ${round} is funded on chain.`);
}

async function main(): Promise<void> {
  await runSetupDemo(parseRound(process.env.DEMO_ROUND ?? ORIGINAL_ROUND), process.env.DEMO_ROOF_IDS);
}

if (require.main === module) {
  main().catch((error: unknown) => { console.error(error); process.exitCode = 1; });
}
