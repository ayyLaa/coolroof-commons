import { readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { ethers, network } from 'hardhat';
import { SPEND_FLAG, spendRefusal } from '../../shared/spend-guard';

// Only the Amoy manifest is committed; a local chain starts empty on every restart, so
// its manifest stays out of git (deployed.localhost.json).
export const DEPLOYMENT_PATH = path.resolve(__dirname, '../..',
  network.name === 'amoy' ? 'deployed.json' : `deployed.${network.name}.json`);
const AMOY_CHAIN_ID = 80002n;
const LOCAL_CHAIN_ID = 31337n;

export interface Deployment {
  address: string;
  chainId: string;
  network: string;
  deployer: string;
  oracle: string;
  transactionHash: string;
}

export function requireAddress(value: string | undefined, name: string): string {
  if (!value || !ethers.isAddress(value) || value === ethers.ZeroAddress) {
    throw new Error(`${name} must be a nonzero Ethereum address`);
  }
  return ethers.getAddress(value);
}

export async function getSupportedChainId(): Promise<bigint> {
  const { chainId } = await ethers.provider.getNetwork();
  // A local Hardhat node is recognised by its chain ID, whatever the network is named
  // (localhost on the host, docker inside compose).
  if (chainId !== AMOY_CHAIN_ID && chainId !== LOCAL_CHAIN_ID) throw new Error('Use Amoy or a local Hardhat network');
  return chainId;
}

/** Called before the first transaction: off a local chain, spending needs ALLOW_MAINNET_SPEND=true. */
export async function requireSpendAllowed(): Promise<void> {
  const { chainId } = await ethers.provider.getNetwork();
  const refusal = spendRefusal(chainId, process.env[SPEND_FLAG]);
  if (refusal) throw new Error(refusal);
}

export async function saveDeployment(deployment: Deployment, filePath: string): Promise<void> {
  await writeFile(filePath, `${JSON.stringify(deployment, null, 2)}\n`, 'utf8');
}

export async function readDeployment(filePath: string): Promise<string> {
  const manifest: unknown = JSON.parse(await readFile(filePath, 'utf8'));
  if (typeof manifest !== 'object' || manifest === null || !('address' in manifest)
    || !('chainId' in manifest) || typeof manifest.address !== 'string') {
    throw new Error('Invalid deployment manifest; run deploy first');
  }
  const chainId = await getSupportedChainId();
  if (manifest.chainId !== chainId.toString()) throw new Error('Deployment chain does not match the connected network');
  return requireDeployedCode(manifest.address);
}

/** The local stack's chain-setup keeps its manifest inside its container, so the host
 * names the escrow by address instead; the code check still guards against a wrong one. */
export async function requireDeployedCode(value: string | undefined): Promise<string> {
  await getSupportedChainId();
  const address = requireAddress(value, 'Deployed contract address');
  if (await ethers.provider.getCode(address) === '0x') throw new Error('No contract at the deployed address');
  return address;
}
