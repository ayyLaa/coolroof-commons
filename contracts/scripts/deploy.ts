import { ethers, network } from 'hardhat';
import { CoolRoofEscrow__factory } from '../typechain-types';
import { DEPLOYMENT_PATH, getSupportedChainId, requireAddress, requireSpendAllowed, saveDeployment } from './lib/deployment';
import type { Deployment } from './lib/deployment';

export async function deployEscrow(oracleAddress: string, filePath = DEPLOYMENT_PATH): Promise<Deployment> {
  const oracle = requireAddress(oracleAddress, 'ORACLE_ADDRESS');
  const chainId = await getSupportedChainId();
  await requireSpendAllowed();
  const [deployer] = await ethers.getSigners();
  if (!deployer) throw new Error('No deployer account configured; set PRIVATE_KEY');
  const escrow = await new CoolRoofEscrow__factory(deployer).deploy(deployer.address);
  await escrow.waitForDeployment();
  console.log(`CoolRoofEscrow deployed: ${await escrow.getAddress()}`);
  await (await escrow.setOracle(oracle)).wait();
  const deployment: Deployment = {
    address: await escrow.getAddress(), chainId: chainId.toString(), network: network.name,
    deployer: deployer.address, oracle, transactionHash: escrow.deploymentTransaction()!.hash,
  };
  await saveDeployment(deployment, filePath);
  console.log(`Oracle configured: ${oracle}\nDeployment saved: ${filePath}`);
  return deployment;
}

async function main(): Promise<void> {
  await deployEscrow(requireAddress(process.env.ORACLE_ADDRESS, 'ORACLE_ADDRESS'));
}

if (require.main === module) {
  main().catch((error: unknown) => { console.error(error); process.exitCode = 1; });
}
