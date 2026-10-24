import { request } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import process from 'node:process'

interface Health {
  network: string
  chain_id: number
  contract_address: string
}

export default async function prepareRound(): Promise<void> {
  const api = await request.newContext()
  try {
    const health = (await (await api.get('http://localhost:4020/health')).json()) as Health
    if (health.network !== 'local' || health.chain_id !== 31337)
      throw new Error('Browser tests require the local chain.')
    const contract = (await (await api.get('http://localhost:8000/contracts/ATH-0142')).json()) as {
      contractor: string
    }
    const response = await api.post('http://localhost:8000/demo/reset')
    if (!response.ok()) throw new Error('Cannot open a local test round.')
    const { round } = (await response.json()) as { round: number }
    fundRound(round, health.contract_address, contract.contractor)
  } finally {
    await api.dispose()
  }
}

function fundRound(round: number, address: string, contractor: string): void {
  const cwd = fileURLToPath(new URL('../../../contracts/', import.meta.url))
  execFileSync(
    process.execPath,
    [
      'node_modules/hardhat/internal/cli/cli.js',
      'setup-demo',
      '--round',
      String(round),
      '--network',
      'docker',
    ],
    {
      cwd,
      timeout: 60_000,
      env: {
        ...process.env,
        CHAIN_RPC_URL: 'http://127.0.0.1:8545',
        CONTRACT_ADDRESS: address,
        CONTRACTOR_ADDRESS: contractor,
      },
      stdio: 'pipe',
    },
  )
}
