import { expect } from 'chai';
import { mkdtemp, readFile, rm, rmdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { ethers } from 'hardhat';
import { deployEscrow } from '../scripts/deploy';
import { selectDemoProjects, setupDemo } from '../scripts/setup-demo';
import { readDeployment } from '../scripts/lib/deployment';
import { DEMO_DEPOSIT, DEMO_PROJECTS, DEMO_THRESHOLDS, QUALITY_PAID_AT_SETUP, TRANCHE } from '../scripts/lib/demo';
import { CoolRoofEscrow__factory } from '../typechain-types';
import { roundRoofId } from '../shared/demo-round';
import { checkRoundBudget, shortfalls } from '../scripts/round-budget';
import { requireSpendAllowed } from '../scripts/lib/deployment';
import { trancheAmounts } from './tranches';

async function withManifest(run: (filePath: string) => Promise<void>): Promise<void> {
  const directory = await mkdtemp(path.join(__dirname, '.deployment-'));
  const filePath = path.join(directory, 'deployed.json');
  try { await run(filePath); }
  finally { await rm(filePath, { force: true }); await rmdir(directory); }
}

async function expectFailure(operation: Promise<unknown>, message: string): Promise<void> {
  let failure: unknown;
  try { await operation; } catch (error: unknown) { failure = error; }
  expect(failure).to.be.instanceOf(Error);
  expect((failure as Error).message).to.contain(message);
}

describe('Deployment and demo scripts', function () {
  it('deploys, configures the oracle after deployment and persists the actual address', async function () {
    await withManifest(async filePath => {
      const [owner, oracle] = await ethers.getSigners();
      const deployment = await deployEscrow(oracle.address, filePath);
      const saved: unknown = JSON.parse(await readFile(filePath, 'utf8'));
      expect(saved).to.deep.equal(deployment);
      expect(deployment.chainId).to.equal('31337');
      const escrow = CoolRoofEscrow__factory.connect(deployment.address, owner);
      expect(await escrow.owner()).to.equal(owner.address);
      expect(await escrow.oracle()).to.equal(oracle.address);
      expect(await readDeployment(filePath)).to.equal(deployment.address);
    });
  });

  it('funds the exact three demo projects and skips matching projects on rerun', async function () {
    await withManifest(async filePath => {
      const [sponsor, oracle, contractor] = await ethers.getSigners();
      const deployment = await deployEscrow(oracle.address, filePath);
      await setupDemo(contractor.address, { filePath });
      const escrow = CoolRoofEscrow__factory.connect(deployment.address, sponsor);
      const deposit = ethers.parseEther(DEMO_DEPOSIT);
      for (const demo of DEMO_PROJECTS) {
        const project = await escrow.getProject(demo.roofId);
        expect(project.sponsor).to.equal(sponsor.address);
        expect(project.contractor).to.equal(contractor.address);
        expect(project.totalAmount).to.equal(deposit);
        expect(project.minNormalizedDeltaCx10).to.equal(DEMO_THRESHOLDS.minNormalizedDeltaCx10);
        expect(project.minCoveragePct).to.equal(DEMO_THRESHOLDS.minCoveragePct);
      }
      for (const demo of DEMO_PROJECTS) {
        const paid = QUALITY_PAID_AT_SETUP.includes(demo.roofId);
        expect(await escrow.getTrancheStatus(demo.roofId, TRANCHE.QUALITY)).to.equal(paid);
      }
      const qualityPaid = (await trancheAmounts(escrow, deposit)).quality * BigInt(QUALITY_PAID_AT_SETUP.length);
      const funded = deposit * BigInt(DEMO_PROJECTS.length) - qualityPaid;
      expect(await ethers.provider.getBalance(escrow)).to.equal(funded);
      const sponsorBalance = await ethers.provider.getBalance(sponsor);
      await setupDemo(contractor.address, { filePath });
      expect(await ethers.provider.getBalance(sponsor)).to.equal(sponsorBalance);
      expect(await ethers.provider.getBalance(escrow)).to.equal(funded);
    });
  });

  it('rejects conflicting demo projects before sending any new deposits', async function () {
    await withManifest(async filePath => {
      const [sponsor, oracle, contractor, otherContractor] = await ethers.getSigners();
      const deployment = await deployEscrow(oracle.address, filePath);
      const escrow = CoolRoofEscrow__factory.connect(deployment.address, sponsor);
      const deposit = ethers.parseEther(DEMO_DEPOSIT);
      await escrow.createProject(DEMO_PROJECTS[1].roofId, otherContractor.address,
        DEMO_THRESHOLDS.minNormalizedDeltaCx10, DEMO_THRESHOLDS.minCoveragePct, { value: deposit });
      await expectFailure(setupDemo(contractor.address, { filePath }), 'does not match demo terms');
      expect(await ethers.provider.getBalance(escrow)).to.equal(deposit);
      await expect(escrow.getProject(DEMO_PROJECTS[0].roofId)).to.be.revertedWithCustomError(escrow, 'ProjectNotFound');
    });
  });

  it('funds only the selected roofs and leaves the others uncreated', async function () {
    await withManifest(async filePath => {
      const [sponsor, oracle, contractor] = await ethers.getSigners();
      const deployment = await deployEscrow(oracle.address, filePath);
      const [success, ...others] = DEMO_PROJECTS;
      await setupDemo(contractor.address, { filePath, projects: selectDemoProjects(success.roofId) });
      const escrow = CoolRoofEscrow__factory.connect(deployment.address, sponsor);
      expect((await escrow.getProject(success.roofId)).totalAmount).to.equal(ethers.parseEther(DEMO_DEPOSIT));
      for (const other of others) {
        await expect(escrow.getProject(other.roofId)).to.be.revertedWithCustomError(escrow, 'ProjectNotFound');
      }
      expect(await ethers.provider.getBalance(escrow)).to.equal(ethers.parseEther(DEMO_DEPOSIT));
    });
  });

  it('funds each round as fresh projects, so every tranche can be paid again', async function () {
    await withManifest(async filePath => {
      const [sponsor, oracle, contractor] = await ethers.getSigners();
      const deployment = await deployEscrow(oracle.address, filePath);
      const escrow = CoolRoofEscrow__factory.connect(deployment.address, sponsor);
      const deposit = ethers.parseEther(DEMO_DEPOSIT);
      await setupDemo(contractor.address, { filePath });
      for (const round of [3, 4]) {
        await setupDemo(contractor.address, { address: deployment.address, round });
        for (const demo of DEMO_PROJECTS) {
          expect((await escrow.getProject(roundRoofId(demo.roofId, round))).totalAmount).to.equal(deposit);
        }
        const storm = roundRoofId(QUALITY_PAID_AT_SETUP[0], round);
        expect(await escrow.getTrancheStatus(storm, TRANCHE.QUALITY)).to.equal(true);
      }
      const sponsorBalance = await ethers.provider.getBalance(sponsor);
      await setupDemo(contractor.address, { address: deployment.address, round: 4 });
      expect(await ethers.provider.getBalance(sponsor)).to.equal(sponsorBalance);
      expect(await escrow.getTrancheStatus(DEMO_PROJECTS[0].roofId, TRANCHE.QUALITY)).to.equal(false);
    });
  });

  it('lets a local chain spend without ALLOW_MAINNET_SPEND', async function () {
    await requireSpendAllowed();
  });

  it('passes the round budget check with funded local wallets', async function () {
    await checkRoundBudget();
  });

  it('names each wallet that cannot pay for a full round', function () {
    const wallets = [
      { role: 'Sponsor', address: '0x1', balanceWei: 10n, costWei: 5n },
      { role: 'Oracle', address: '0x2', balanceWei: 1n, costWei: ethers.parseEther('0.002') + 1n },
    ];
    expect(shortfalls(wallets)).to.deep.equal(['Oracle needs 0.002 POL more']);
  });

  it('rejects a round that is not a whole number before any transaction', async function () {
    const [, , contractor] = await ethers.getSigners();
    await expectFailure(setupDemo(contractor.address, { round: -1 }), 'round must be a whole number');
  });

  it('rejects unknown demo roof IDs before any transaction', function () {
    expect(() => selectDemoProjects('ATH-0142, ATH-9999')).to.throw('Unknown demo roof IDs: ATH-9999');
    expect(selectDemoProjects(undefined)).to.equal(DEMO_PROJECTS);
  });

  it('rejects wrong-chain manifests and addresses without deployed code', async function () {
    await withManifest(async filePath => {
      const [account] = await ethers.getSigners();
      await writeFile(filePath, JSON.stringify({ address: account.address, chainId: '80002' }));
      await expectFailure(readDeployment(filePath), 'does not match');
      await writeFile(filePath, JSON.stringify({ address: account.address, chainId: '31337' }));
      await expectFailure(readDeployment(filePath), 'No contract');
    });
  });
});
