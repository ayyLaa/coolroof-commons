import { expect } from 'chai';
import { ethers } from 'hardhat';
import { loadFixture, time } from '@nomicfoundation/hardhat-network-helpers';
import type { ContractTransactionResponse } from 'ethers';
import type { CoolRoofEscrow } from '../typechain-types';
import { CoolRoofEscrow__factory, PaymentReceiver__factory } from '../typechain-types';
import { APPROVED_STATUS, DEMO_DEPOSIT, DEMO_PROJECTS, DEMO_ROOF_IDS, DEMO_THRESHOLDS, TRANCHE } from '../scripts/lib/demo';
import { durabilityDelaySeconds } from '../scripts/lib/thresholds';
import { trancheAmounts } from './tranches';
import { FORCE_MAJEURE_STATUS, VERIFICATION_STATUS } from '../shared/status';
import thresholds from '../../schema/thresholds.json';

const ROOF = 'roof-001';
const DEPOSIT = 1000n;
const { QUALITY, DURABILITY, FORCE_MAJEURE_RESERVE: RESERVE } = TRANCHE;
// Thresholds come from schema/thresholds.json through the one x10 conversion.
const MIN_DELTA = DEMO_THRESHOLDS.minNormalizedDeltaCx10;
const MIN_COVERAGE = DEMO_THRESHOLDS.minCoveragePct;
// One step past each threshold, in the contract's units.
const WEAKER_DELTA = MIN_DELTA + 1;
const LOWER_COVERAGE = MIN_COVERAGE - 1;
const DAY = 24n * 60n * 60n;
const DURABILITY_DELAY = durabilityDelaySeconds();
const RECLAIM_DELAY = 365n * DAY;
const EVIDENCE = ethers.keccak256(ethers.toUtf8Bytes('off-chain evidence'));
const DEVICE_SIGNATURE = '0x1234';
// 24.0 m/s gusts and 68.0 mm of rain, multiplied by ten as the escrow expects.
const STORM_GUST_X10 = 240;
const STORM_PRECIP_X10 = 680;

interface Submission {
  phase?: number; delta?: number; coverage?: number; forceMajeure?: boolean;
  status?: number; roofId?: string; gustX10?: number; precipX10?: number;
  measurementId?: string; measuredAt?: bigint;
}

async function verify(escrow: CoolRoofEscrow, submission: Submission = {}): Promise<ContractTransactionResponse> {
  const {
    phase = QUALITY, delta = MIN_DELTA, coverage = MIN_COVERAGE, forceMajeure = false,
    status = forceMajeure ? FORCE_MAJEURE_STATUS : APPROVED_STATUS, roofId = ROOF,
    gustX10 = forceMajeure ? STORM_GUST_X10 : 0, precipX10 = forceMajeure ? STORM_PRECIP_X10 : 0,
  } = submission;
  return escrow.submitVerification(roofId, status, delta, coverage, forceMajeure, phase, EVIDENCE,
    DEVICE_SIGNATURE, gustX10, precipX10, submission.measurementId ?? ethers.id(`${roofId}:${phase}`),
    submission.measuredAt ?? BigInt(await time.latest()));
}

async function emptyEscrowFixture() {
  const [owner, oracle, sponsor, contractor, stranger] = await ethers.getSigners();
  const escrow = await new CoolRoofEscrow__factory(owner).deploy(oracle.address);
  return { escrow, owner, oracle, sponsor, contractor, stranger };
}

async function deployFixture() {
  const fixture = await emptyEscrowFixture();
  await fixture.escrow.connect(fixture.sponsor)
    .createProject(ROOF, fixture.contractor.address, MIN_DELTA, MIN_COVERAGE, { value: DEPOSIT });
  return fixture;
}

async function qualityFixture() {
  const fixture = await deployFixture();
  await verify(fixture.escrow.connect(fixture.oracle));
  return fixture;
}

async function matureFixture() {
  const fixture = await qualityFixture();
  const project = await fixture.escrow.getProject(ROOF);
  await time.increaseTo(project.qualityReleasedAt + DURABILITY_DELAY);
  return fixture;
}

describe('CoolRoofEscrow', function () {
  it('locks sponsor funds and records immutable creation terms', async function () {
    const { escrow, sponsor, contractor } = await loadFixture(deployFixture);
    const project = await escrow.getProject(ROOF);
    expect(project.sponsor).to.equal(sponsor.address);
    expect(project.contractor).to.equal(contractor.address);
    expect(project.totalAmount).to.equal(DEPOSIT);
    expect(project.minNormalizedDeltaCx10).to.equal(MIN_DELTA);
    expect(project.minCoveragePct).to.equal(MIN_COVERAGE);
    expect(project.exists).to.equal(true);
    expect(project.qualityReleasedAt).to.equal(0n);
    expect(await ethers.provider.getBalance(escrow)).to.equal(DEPOSIT);
    await expect(escrow.createProject(ROOF, contractor, -100, 90, { value: DEPOSIT }))
      .to.be.revertedWithCustomError(escrow, 'ProjectAlreadyExists');
  });

  it('uses the durability delay schema/thresholds.json defines', async function () {
    const { escrow } = await loadFixture(deployFixture);
    expect(await escrow.DURABILITY_DELAY()).to.equal(DURABILITY_DELAY);
  });

  it('emits project creation with the actual depositor and amount', async function () {
    const { escrow, sponsor, contractor } = await loadFixture(deployFixture);
    await expect(escrow.connect(sponsor).createProject('second', contractor, -90, 90, { value: DEPOSIT }))
      .to.emit(escrow, 'ProjectCreated').withArgs('second', sponsor.address, contractor.address, DEPOSIT);
  });

  it('rejects invalid creation terms and zero oracle addresses', async function () {
    const { escrow, contractor } = await loadFixture(deployFixture);
    await expect(escrow.createProject('', contractor, MIN_DELTA, MIN_COVERAGE, { value: DEPOSIT }))
      .to.be.revertedWithCustomError(escrow, 'InvalidRoofId');
    await expect(escrow.createProject('new', ethers.ZeroAddress, MIN_DELTA, MIN_COVERAGE, { value: DEPOSIT }))
      .to.be.revertedWithCustomError(escrow, 'InvalidAddress');
    await expect(escrow.createProject('new', contractor, MIN_DELTA, MIN_COVERAGE, { value: 0 }))
      .to.be.revertedWithCustomError(escrow, 'InvalidDeposit');
    for (const [delta, coverage] of [[0, MIN_COVERAGE], [1, MIN_COVERAGE], [MIN_DELTA, 0], [MIN_DELTA, 101]]) {
      await expect(escrow.createProject('new', contractor, delta, coverage, { value: DEPOSIT }))
        .to.be.revertedWithCustomError(escrow, 'InvalidThresholds');
    }
    await expect(ethers.deployContract('CoolRoofEscrow', [ethers.ZeroAddress]))
      .to.be.revertedWithCustomError(escrow, 'InvalidAddress');
  });

  it('restricts verification to the oracle and oracle rotation to the owner', async function () {
    const { escrow, oracle, stranger } = await loadFixture(deployFixture);
    await expect(verify(escrow.connect(stranger)))
      .to.be.revertedWithCustomError(escrow, 'UnauthorizedOracle').withArgs(stranger.address);
    await expect(escrow.connect(stranger).setOracle(stranger.address))
      .to.be.revertedWithCustomError(escrow, 'OwnableUnauthorizedAccount');
    await expect(escrow.setOracle(ethers.ZeroAddress)).to.be.revertedWithCustomError(escrow, 'InvalidAddress');
    await expect(escrow.setOracle(stranger.address)).to.emit(escrow, 'OracleUpdated').withArgs(oracle.address, stranger.address);
    await expect(verify(escrow.connect(oracle))).to.be.revertedWithCustomError(escrow, 'UnauthorizedOracle');
    await verify(escrow.connect(stranger));
  });

  it('releases exactly 60% at inclusive thresholds and retains evidence on chain', async function () {
    const { escrow, oracle, contractor } = await loadFixture(deployFixture);
    const transaction = verify(escrow.connect(oracle));
    await expect(transaction).to.changeEtherBalances([escrow, contractor], [-600n, 600n]);
    await expect(transaction).to.emit(escrow, 'VerificationSubmitted').withArgs(ROOF, APPROVED_STATUS, MIN_DELTA, EVIDENCE);
    await expect(transaction).to.emit(escrow, 'VerificationEvidence')
      .withArgs(ROOF, QUALITY, MIN_COVERAGE, false, DEVICE_SIGNATURE);
    await expect(transaction).to.emit(escrow, 'TrancheReleased').withArgs(ROOF, QUALITY, 600n, contractor.address);
    expect(await escrow.getTrancheStatus(ROOF, QUALITY)).to.equal(true);
    expect((await escrow.getProject(ROOF)).qualityReleasedAt).to.equal(await time.latest());
  });

  for (const [label, delta, coverage] of [
    ['insufficient cooling', WEAKER_DELTA, MIN_COVERAGE], ['insufficient coverage', MIN_DELTA, LOWER_COVERAGE],
    ['positive delta', -MIN_DELTA, 100],
  ] as const) {
    it(`holds funds despite oracle success status: ${label}`, async function () {
      const { escrow, oracle } = await loadFixture(deployFixture);
      await expect(verify(escrow.connect(oracle), { delta, coverage }))
        .to.emit(escrow, 'PaymentHeld').withArgs(ROOF, QUALITY, 'Measurement thresholds not met');
      expect(await escrow.getTrancheStatus(ROOF, QUALITY)).to.equal(false);
      expect(await ethers.provider.getBalance(escrow)).to.equal(DEPOSIT);
      await verify(escrow.connect(oracle), { delta: -100, coverage: 100 });
      expect(await escrow.getTrancheStatus(ROOF, QUALITY)).to.equal(true);
    });
  }

  for (const status of [VERIFICATION_STATUS.flagged, VERIFICATION_STATUS.insufficient_data, 255, FORCE_MAJEURE_STATUS]) {
    it(`holds passing measurements with unapproved status ${status}`, async function () {
      const { escrow, oracle, contractor } = await loadFixture(deployFixture);
      const tx = verify(escrow.connect(oracle), { status });
      await expect(tx).to.emit(escrow, 'PaymentHeld').withArgs(ROOF, QUALITY, 'Verification not approved');
      await expect(tx).not.to.emit(escrow, 'TrancheReleased');
      await expect(tx).to.changeEtherBalance(contractor, 0);
      expect(await escrow.getTrancheStatus(ROOF, QUALITY)).to.equal(false);
    });
  }

  it('keeps status and storm limits aligned with the shared configuration', async function () {
    const { escrow } = await loadFixture(deployFixture);
    expect(await escrow.APPROVED_STATUS()).to.equal(VERIFICATION_STATUS.approved);
    expect(await escrow.FORCE_MAJEURE_STATUS()).to.equal(FORCE_MAJEURE_STATUS);
    expect(await escrow.FORCE_MAJEURE_GUST_MS_X10()).to.equal(thresholds.default.force_majeure_gust_ms * 10);
    expect(await escrow.FORCE_MAJEURE_PRECIP_MM_X10()).to.equal(thresholds.default.force_majeure_precip_mm * 10);
  });

  for (const [gustX10, precipX10] of [[0, 0], [200, 500], [199, 499]]) {
    it(`refuses a storm with gust ${gustX10} and rain ${precipX10}`, async function () {
      const { escrow, oracle, contractor } = await loadFixture(qualityFixture);
      const tx = verify(escrow.connect(oracle), { phase: DURABILITY, forceMajeure: true, gustX10, precipX10 });
      await expect(tx).not.to.emit(escrow, 'TrancheReleased');
      await expect(tx).to.changeEtherBalance(contractor, 0);
      expect(await escrow.isDurabilitySuspended(ROOF)).to.equal(false);
    });
  }

  it('does not pay a storm submitted with the ordinary approved status', async function () {
    const { escrow, oracle, contractor } = await loadFixture(qualityFixture);
    await expect(verify(escrow.connect(oracle), { phase: DURABILITY, forceMajeure: true, status: APPROVED_STATUS }))
      .to.changeEtherBalance(contractor, 0);
    expect(await escrow.getTrancheStatus(ROOF, RESERVE)).to.equal(false);
  });

  for (const [gustX10, precipX10] of [[201, 0], [0, 501]]) {
    it(`accepts an independently sufficient storm value: ${gustX10}, ${precipX10}`, async function () {
      const { escrow, oracle, contractor } = await loadFixture(qualityFixture);
      await expect(verify(escrow.connect(oracle), { phase: DURABILITY, forceMajeure: true, gustX10, precipX10 }))
        .to.changeEtherBalance(contractor, 100n);
    });
  }

  it('rejects nonexistent projects, invalid phases, impossible coverage and quality force majeure', async function () {
    const { escrow, oracle } = await loadFixture(deployFixture);
    const connected = escrow.connect(oracle);
    await expect(verify(connected, { roofId: 'missing' })).to.be.revertedWithCustomError(escrow, 'ProjectNotFound');
    await expect(escrow.getProject('missing')).to.be.revertedWithCustomError(escrow, 'ProjectNotFound');
    await expect(escrow.getTrancheStatus('missing', QUALITY)).to.be.revertedWithCustomError(escrow, 'ProjectNotFound');
    await expect(verify(connected, { phase: RESERVE })).to.be.revertedWithCustomError(escrow, 'InvalidPhase');
    await expect(verify(connected, { coverage: 101 })).to.be.revertedWithCustomError(escrow, 'InvalidCoverage');
    await expect(verify(connected, { forceMajeure: true })).to.be.revertedWithCustomError(escrow, 'InvalidForceMajeurePhase');
  });

  it('requires quality before any durability-phase payment', async function () {
    const { escrow, oracle } = await loadFixture(deployFixture);
    for (const forceMajeure of [false, true]) {
      await expect(verify(escrow.connect(oracle), { phase: DURABILITY, forceMajeure }))
        .to.emit(escrow, 'PaymentHeld').withArgs(ROOF, DURABILITY, 'Quality tranche not released');
    }
    expect(await ethers.provider.getBalance(escrow)).to.equal(DEPOSIT);
  });

  it('holds durability until precisely 180 days after the quality payment', async function () {
    const { escrow, oracle, contractor } = await loadFixture(qualityFixture);
    const unlockAt = (await escrow.getProject(ROOF)).qualityReleasedAt + DURABILITY_DELAY;
    await time.setNextBlockTimestamp(unlockAt - 1n);
    await expect(verify(escrow.connect(oracle), { phase: DURABILITY }))
      .to.emit(escrow, 'PaymentHeld').withArgs(ROOF, DURABILITY, 'Durability period not elapsed');
    await time.setNextBlockTimestamp(unlockAt);
    await expect(verify(escrow.connect(oracle), { phase: DURABILITY, measuredAt: unlockAt }))
      .to.changeEtherBalances([escrow, contractor], [-300n, 300n]);
    expect(await escrow.getTrancheStatus(ROOF, DURABILITY)).to.equal(true);
    expect(await ethers.provider.getBalance(escrow)).to.equal(100n);
  });

  it('starts the durability clock at the quality payment, not at project creation', async function () {
    const { escrow, oracle } = await loadFixture(deployFixture);
    const createdAt = (await escrow.getProject(ROOF)).createdAt;
    await time.increaseTo(createdAt + 100n * DAY);
    await verify(escrow.connect(oracle));
    await time.increaseTo(createdAt + DURABILITY_DELAY);
    await expect(verify(escrow.connect(oracle), { phase: DURABILITY }))
      .to.emit(escrow, 'PaymentHeld').withArgs(ROOF, DURABILITY, 'Durability period not elapsed');
  });

  it('independently checks both durability measurements after the delay', async function () {
    const { escrow, oracle } = await loadFixture(matureFixture);
    for (const [delta, coverage] of [[WEAKER_DELTA, MIN_COVERAGE], [MIN_DELTA, LOWER_COVERAGE]]) {
      await expect(verify(escrow.connect(oracle), { phase: DURABILITY, delta, coverage }))
        .to.emit(escrow, 'PaymentHeld').withArgs(ROOF, DURABILITY, 'Measurement thresholds not met');
    }
    expect(await ethers.provider.getBalance(escrow)).to.equal(400n);
  });

  it('refuses the quality measurement identity even after the durability delay', async function () {
    const { escrow, oracle, contractor } = await loadFixture(matureFixture);
    const tx = verify(escrow.connect(oracle), { phase: DURABILITY, measurementId: ethers.id(`${ROOF}:${QUALITY}`) });
    await expect(tx).to.emit(escrow, 'PaymentHeld').withArgs(ROOF, DURABILITY, 'A new durability measurement is required');
    await expect(tx).to.changeEtherBalance(contractor, 0);
  });

  it('refuses a different measurement taken before durability eligibility', async function () {
    const { escrow, oracle, contractor } = await loadFixture(matureFixture);
    const eligibleAt = (await escrow.getProject(ROOF)).qualityReleasedAt + DURABILITY_DELAY;
    const tx = verify(escrow.connect(oracle), { phase: DURABILITY, measuredAt: eligibleAt - 1n });
    await expect(tx).to.emit(escrow, 'PaymentHeld').withArgs(ROOF, DURABILITY, 'Durability measurement predates eligibility');
    await expect(tx).to.changeEtherBalance(contractor, 0);
  });

  it('refuses missing identity and future measurement timestamps', async function () {
    const { escrow, oracle, contractor } = await loadFixture(deployFixture);
    await expect(verify(escrow.connect(oracle), { measurementId: ethers.ZeroHash })).to.changeEtherBalance(contractor, 0);
    await expect(verify(escrow.connect(oracle), { measuredAt: BigInt(await time.latest()) + DAY })).to.changeEtherBalance(contractor, 0);
  });

  it('pays the 10% reserve on force majeure, reports the weather and suspends durability', async function () {
    const { escrow, oracle, contractor } = await loadFixture(qualityFixture);
    const transaction = verify(escrow.connect(oracle), {
      phase: DURABILITY, delta: 0, coverage: 0, forceMajeure: true, gustX10: STORM_GUST_X10, precipX10: STORM_PRECIP_X10,
    });
    await expect(transaction).to.changeEtherBalances([escrow, contractor], [-100n, 100n]);
    await expect(transaction).to.emit(escrow, 'ForceMajeureApplied').withArgs(ROOF, STORM_GUST_X10, STORM_PRECIP_X10);
    await expect(transaction).to.emit(escrow, 'PaymentHeld').withArgs(ROOF, DURABILITY, 'Durability suspended by force majeure');
    expect(await escrow.getTrancheStatus(ROOF, RESERVE)).to.equal(true);
    expect(await escrow.getTrancheStatus(ROOF, DURABILITY)).to.equal(false);
    expect(await escrow.isDurabilitySuspended(ROOF)).to.equal(true);
    expect(await ethers.provider.getBalance(escrow)).to.equal(300n);
    for (const forceMajeure of [true, false]) {
      await expect(verify(escrow.connect(oracle), { phase: DURABILITY, forceMajeure }))
        .to.be.revertedWithCustomError(escrow, 'PhaseAlreadySettled');
    }
  });

  it('prevents replay and a second durability-phase payout through force majeure', async function () {
    const { escrow, oracle } = await loadFixture(matureFixture);
    await expect(verify(escrow.connect(oracle))).to.be.revertedWithCustomError(escrow, 'PhaseAlreadySettled');
    await verify(escrow.connect(oracle), { phase: DURABILITY });
    for (const forceMajeure of [false, true]) {
      await expect(verify(escrow.connect(oracle), { phase: DURABILITY, forceMajeure }))
        .to.be.revertedWithCustomError(escrow, 'PhaseAlreadySettled');
    }
  });

  it('keeps allocations isolated and assigns rounding dust to the reserve', async function () {
    const { escrow, oracle, contractor } = await loadFixture(deployFixture);
    const oddRoof = 'odd-deposit';
    await escrow.createProject(oddRoof, contractor, MIN_DELTA, MIN_COVERAGE, { value: 101n });
    await expect(verify(escrow.connect(oracle), { roofId: oddRoof })).to.changeEtherBalance(contractor, 60n);
    await expect(verify(escrow.connect(oracle), { roofId: oddRoof, phase: DURABILITY, delta: 0, coverage: 0, forceMajeure: true }))
      .to.changeEtherBalance(contractor, 11n);
    expect(await ethers.provider.getBalance(escrow)).to.equal(DEPOSIT + 30n);
    expect(await escrow.getTrancheStatus(ROOF, QUALITY)).to.equal(false);
  });

  it('blocks reentrancy even when the receiving contractor is also the oracle', async function () {
    const { escrow, owner } = await loadFixture(deployFixture);
    const receiver = await new PaymentReceiver__factory(owner).deploy(escrow, MIN_DELTA, MIN_COVERAGE);
    await escrow.createProject('callback', receiver, MIN_DELTA, MIN_COVERAGE, { value: DEPOSIT });
    await escrow.setOracle(await receiver.getAddress());
    await receiver.verify();
    expect(await receiver.reentrySucceeded()).to.equal(false);
    expect(await receiver.reentryError()).to.equal(escrow.interface.getError('ReentrancyGuardReentrantCall')!.selector);
    expect(await ethers.provider.getBalance(receiver)).to.equal(600n);
  });

  it('rolls back tranche state and funds on a rejected payment, allowing a retry', async function () {
    const { escrow, oracle, owner } = await loadFixture(deployFixture);
    const receiver = await new PaymentReceiver__factory(owner).deploy(escrow, MIN_DELTA, MIN_COVERAGE);
    await escrow.createProject('callback', receiver, MIN_DELTA, MIN_COVERAGE, { value: DEPOSIT });
    await receiver.setRejectPayment(true);
    await expect(verify(escrow.connect(oracle), { roofId: 'callback' }))
      .to.be.revertedWithCustomError(escrow, 'PaymentFailed');
    expect(await escrow.getTrancheStatus('callback', QUALITY)).to.equal(false);
    expect(await ethers.provider.getBalance(escrow)).to.equal(2n * DEPOSIT);
    await receiver.setRejectPayment(false);
    await verify(escrow.connect(oracle), { roofId: 'callback' });
    expect(await escrow.getTrancheStatus('callback', QUALITY)).to.equal(true);
  });
});

describe('CoolRoofEscrow sponsor reclaim', function () {
  it('protects the entire contractor claim window without requiring a prior durability claim', async function () {
    const { escrow, oracle, sponsor } = await loadFixture(deployFixture);
    const createdAt = (await escrow.getProject(ROOF)).createdAt;
    await time.increaseTo(createdAt + 250n * DAY);
    await verify(escrow.connect(oracle));
    const availableAt = (await escrow.getProject(ROOF)).qualityReleasedAt + DURABILITY_DELAY + 30n * DAY;
    expect(await escrow.DURABILITY_CLAIM_WINDOW()).to.equal(BigInt(thresholds.settlement.durability_claim_days) * DAY);
    await time.setNextBlockTimestamp(availableAt - 1n);
    await expect(escrow.connect(sponsor).reclaimUnreleased(ROOF)).to.be.revertedWithCustomError(escrow, 'ReclaimNotYetAvailable');
    await time.setNextBlockTimestamp(availableAt);
    await expect(escrow.connect(sponsor).reclaimUnreleased(ROOF)).to.changeEtherBalance(sponsor, 400n);
  });
  it('protects late quality payments until the durability window closes', async function () {
    const { escrow, oracle, sponsor, contractor } = await loadFixture(deployFixture);
    const { createdAt } = await escrow.getProject(ROOF);
    await time.setNextBlockTimestamp(createdAt + 250n * DAY);
    await verify(escrow.connect(oracle));
    const { qualityReleasedAt } = await escrow.getProject(ROOF);
    await time.setNextBlockTimestamp(createdAt + 365n * DAY);
    await expect(escrow.connect(sponsor).reclaimUnreleased(ROOF))
      .to.be.revertedWithCustomError(escrow, 'ReclaimNotYetAvailable')
      .withArgs(qualityReleasedAt + DURABILITY_DELAY + 30n * DAY);
    await time.setNextBlockTimestamp(qualityReleasedAt + DURABILITY_DELAY - 1n);
    await expect(escrow.connect(sponsor).reclaimUnreleased(ROOF)).to.be.revertedWithCustomError(escrow, 'ReclaimNotYetAvailable');
    await time.setNextBlockTimestamp(qualityReleasedAt + DURABILITY_DELAY);
    await expect(verify(escrow.connect(oracle), { phase: DURABILITY, measuredAt: qualityReleasedAt + DURABILITY_DELAY })).to.changeEtherBalance(contractor, 300n);
    await time.increaseTo(qualityReleasedAt + DURABILITY_DELAY + 30n * DAY);
    await expect(escrow.connect(sponsor).reclaimUnreleased(ROOF)).to.changeEtherBalance(sponsor, 100n);
  });
  async function reclaimAt(days: bigint) {
    const fixture = await loadFixture(deployFixture);
    const { createdAt } = await fixture.escrow.getProject(ROOF);
    await time.setNextBlockTimestamp(createdAt + days * DAY);
    return { ...fixture, reclaim: fixture.escrow.connect(fixture.sponsor).reclaimUnreleased(ROOF), createdAt };
  }

  it('reverts on day 364', async function () {
    const { escrow, reclaim, createdAt } = await reclaimAt(364n);
    await expect(reclaim).to.be.revertedWithCustomError(escrow, 'ReclaimNotYetAvailable')
      .withArgs(createdAt + RECLAIM_DELAY);
    expect(await ethers.provider.getBalance(escrow)).to.equal(DEPOSIT);
  });

  it('returns every unpaid tranche to the sponsor on day 366', async function () {
    const { escrow, sponsor, reclaim } = await reclaimAt(366n);
    await expect(reclaim).to.changeEtherBalances([escrow, sponsor], [-DEPOSIT, DEPOSIT]);
    await expect(reclaim).to.emit(escrow, 'UnreleasedReclaimed').withArgs(ROOF, sponsor.address, DEPOSIT);
    expect(await escrow.isReclaimed(ROOF)).to.equal(true);
  });

  it('returns only what the contractor was not paid', async function () {
    const { escrow, oracle, sponsor } = await loadFixture(qualityFixture);
    await verify(escrow.connect(oracle), { phase: DURABILITY, forceMajeure: true });
    await time.increaseTo((await escrow.getProject(ROOF)).createdAt + RECLAIM_DELAY);
    await expect(escrow.connect(sponsor).reclaimUnreleased(ROOF)).to.changeEtherBalances([escrow, sponsor], [-300n, 300n]);
  });

  it('only lets the project sponsor reclaim', async function () {
    const { escrow, contractor } = await loadFixture(deployFixture);
    await time.increase(RECLAIM_DELAY);
    await expect(escrow.connect(contractor).reclaimUnreleased(ROOF))
      .to.be.revertedWithCustomError(escrow, 'NotProjectSponsor').withArgs(contractor.address);
  });

  it('closes the project to further verifications and reclaims', async function () {
    const { escrow, oracle, sponsor, reclaim } = await reclaimAt(366n);
    await reclaim;
    await expect(escrow.connect(sponsor).reclaimUnreleased(ROOF)).to.be.revertedWithCustomError(escrow, 'ProjectClosed');
    await expect(verify(escrow.connect(oracle))).to.be.revertedWithCustomError(escrow, 'ProjectClosed');
  });
});

describe('CoolRoofEscrow demo scenarios', function () {
  const DEMO_AMOUNT = ethers.parseEther(DEMO_DEPOSIT);
  const [SUCCESS, POOR_COATING, STORM] = DEMO_PROJECTS;
  type DemoProject = typeof DEMO_PROJECTS[number];

  async function createProject(project: DemoProject) {
    const fixture = await loadFixture(emptyEscrowFixture);
    await fixture.escrow.connect(fixture.sponsor).createProject(project.roofId, fixture.contractor.address,
      DEMO_THRESHOLDS.minNormalizedDeltaCx10, DEMO_THRESHOLDS.minCoveragePct, { value: DEMO_AMOUNT });
    return { ...fixture, payments: await trancheAmounts(fixture.escrow, DEMO_AMOUNT) };
  }

  function submit(escrow: CoolRoofEscrow, project: DemoProject, submission: Submission = {}) {
    return verify(escrow, { delta: project.normalizedDeltaCx10, coverage: project.coveragePct, roofId: project.roofId, ...submission });
  }

  it('uses the same ATH roof IDs as the backend and the oracle', function () {
    expect(DEMO_PROJECTS.map(project => project.roofId)).to.deep.equal(['ATH-0142', 'ATH-0287', 'ATH-0355']);
    expect(DEMO_PROJECTS.map(project => project.roofId)).to.deep.equal([...DEMO_ROOF_IDS]);
  });

  it('splits the 0.001 demo deposit 0.0006 / 0.0003 / 0.0001 with nothing left over', async function () {
    const { payments } = await createProject(SUCCESS);
    expect(DEMO_AMOUNT).to.equal(ethers.parseEther('0.001'));
    expect(payments).to.deep.equal({
      quality: ethers.parseEther('0.0006'), durability: ethers.parseEther('0.0003'), reserve: ethers.parseEther('0.0001'),
    });
    expect(payments.quality + payments.durability + payments.reserve).to.equal(DEMO_AMOUNT);
  });

  it('Successful intervention: pays 60% quality and 30% durability 180 days later', async function () {
    const { escrow, oracle, contractor, payments } = await createProject(SUCCESS);
    await expect(submit(escrow.connect(oracle), SUCCESS))
      .to.changeEtherBalances([escrow, contractor], [-payments.quality, payments.quality]);
    await time.increase(DURABILITY_DELAY);
    const durability = submit(escrow.connect(oracle), SUCCESS, { phase: DURABILITY });
    await expect(durability).to.changeEtherBalances([escrow, contractor], [-payments.durability, payments.durability]);
    await expect(durability).to.emit(escrow, 'TrancheReleased')
      .withArgs(SUCCESS.roofId, DURABILITY, payments.durability, contractor.address);
    expect(await ethers.provider.getBalance(escrow)).to.equal(payments.reserve);
  });

  it('Poor coating: delta -32 and coverage 41 hold the full deposit', async function () {
    const { escrow, oracle, contractor } = await createProject(POOR_COATING);
    const transaction = submit(escrow.connect(oracle), POOR_COATING);
    await expect(transaction).to.emit(escrow, 'PaymentHeld')
      .withArgs(POOR_COATING.roofId, QUALITY, 'Measurement thresholds not met');
    await expect(transaction).not.to.emit(escrow, 'TrancheReleased');
    await expect(transaction).to.changeEtherBalance(contractor, 0);
    expect(await ethers.provider.getBalance(escrow)).to.equal(DEMO_AMOUNT);
  });

  it('Storm: pays quality, then releases the reserve with the storm readings', async function () {
    const { escrow, oracle, contractor, payments } = await createProject(STORM);
    await expect(submit(escrow.connect(oracle), STORM)).to.changeEtherBalance(contractor, payments.quality);
    const storm = submit(escrow.connect(oracle), STORM, {
      phase: DURABILITY, forceMajeure: true, gustX10: STORM_GUST_X10, precipX10: STORM_PRECIP_X10,
    });
    await expect(storm).to.changeEtherBalances([escrow, contractor], [-payments.reserve, payments.reserve]);
    await expect(storm).to.emit(escrow, 'ForceMajeureApplied').withArgs(STORM.roofId, STORM_GUST_X10, STORM_PRECIP_X10);
    expect(await escrow.isDurabilitySuspended(STORM.roofId)).to.equal(true);
    expect(await ethers.provider.getBalance(escrow)).to.equal(payments.durability);
  });

  for (const [label, delta, coverage] of [['cooling alone fails', -32, 94], ['coverage alone fails', -111, 41]] as const) {
    it(`holds oracle-approved data when ${label}`, async function () {
      const { escrow, oracle, contractor } = await createProject(SUCCESS);
      const transaction = submit(escrow.connect(oracle), SUCCESS, { delta, coverage });
      await expect(transaction).to.emit(escrow, 'VerificationSubmitted').withArgs(SUCCESS.roofId, APPROVED_STATUS, delta, EVIDENCE);
      await expect(transaction).to.emit(escrow, 'PaymentHeld')
        .withArgs(SUCCESS.roofId, QUALITY, 'Measurement thresholds not met');
      await expect(transaction).to.changeEtherBalance(contractor, 0);
    });
  }
});
