import 'dotenv/config';
import '@nomicfoundation/hardhat-toolbox';
import { task, types } from 'hardhat/config';
import type { HardhatUserConfig } from 'hardhat/config';

// `hardhat run` takes no script arguments, so a task carries --round. Imported inside the
// action: the script needs the runtime this config is still building.
task('setup-demo', 'Creates and funds the demo projects of one round')
  .addOptionalParam('round', 'Demo round; 0 is the unsuffixed original projects', 0, types.int)
  .addOptionalParam('roofs', 'Comma-separated demo roof IDs (default: all three)', undefined, types.string)
  .setAction(async ({ round, roofs }: { round: number; roofs?: string }) => {
    const { runSetupDemo } = await import('./scripts/setup-demo');
    await runSetupDemo(round, roofs);
  });

const privateKey = process.env.PRIVATE_KEY?.trim();
// Only setup-demo needs it: the storm project's quality verification must come from the oracle.
const oraclePrivateKey = process.env.ORACLE_PRIVATE_KEY?.trim();
const config: HardhatUserConfig = {
  solidity: {
    version: '0.8.24',
    settings: { optimizer: { enabled: true, runs: 200 }, viaIR: true },
  },
  networks: {
    // Simulated visits extend into January 2027; real networks keep their own clock.
    hardhat: { initialDate: '2027-02-01T00:00:00Z' },
    // The compose chain service; its node's own unlocked test accounts sign.
    docker: { url: process.env.CHAIN_RPC_URL || 'http://chain:8545' },
    amoy: {
      url: process.env.AMOY_RPC_URL || 'https://rpc-amoy.polygon.technology',
      chainId: 80002,
      accounts: [privateKey, oraclePrivateKey].filter((key): key is string => Boolean(key)),
    },
  },
  etherscan: { apiKey: process.env.POLYGONSCAN_API_KEY || '' },
};
export default config;
