import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { makeError } from 'ethers';
import { sendVerification } from '../src/chain';
import { mapVerification } from '../src/verification';
import { escrowInterface } from '../src/abi';
import { ADDRESS, eventLog, TX_HASH, VERIFICATION } from './fixtures';

const mocks = vi.hoisted(() => ({ send: vi.fn(), getCode: vi.fn(), destroy: vi.fn(), wait: vi.fn(), getNetwork: vi.fn() }));
vi.mock('ethers', async importOriginal => {
  const actual = await importOriginal<typeof import('ethers')>();
  return { ...actual,
    JsonRpcProvider: class { getCode = mocks.getCode; destroy = mocks.destroy; getNetwork = mocks.getNetwork; },
    Contract: class { getFunction(): typeof mocks.send { return mocks.send; } },
  };
});

const config = { backendUrl: 'http://backend', rpcUrl: 'http://rpc', contractAddress: ADDRESS, eventsFromBlock: 0 };
const verification = mapVerification(VERIFICATION, 'ATH-0142', 'quality');

beforeEach(() => {
  vi.resetAllMocks();
  vi.stubEnv('ORACLE_PRIVATE_KEY', `0x${'01'.repeat(32)}`);
  mocks.getCode.mockResolvedValue('0x6000');
  mocks.getNetwork.mockResolvedValue({ chainId: 31337n });
  mocks.send.mockResolvedValue({ hash: TX_HASH, wait: mocks.wait });
  mocks.wait.mockResolvedValue({ hash: TX_HASH, blockNumber: 42, status: 1, logs: [] });
});
afterEach(() => vi.unstubAllEnvs());

describe('Spend guard', () => {
  it('refuses to sign on Amoy without ALLOW_MAINNET_SPEND and sends nothing', async () => {
    mocks.getNetwork.mockResolvedValue({ chainId: 80002n });
    await expect(sendVerification(config, verification)).rejects.toMatchObject({
      code: 'SPEND_NOT_ALLOWED', message: 'Refusing to spend real POL on Amoy. Set ALLOW_MAINNET_SPEND=true to proceed.',
    });
    expect(mocks.send).not.toHaveBeenCalled();
    expect(mocks.destroy).toHaveBeenCalledOnce();
  });

  it('sends on Amoy once ALLOW_MAINNET_SPEND=true, and on a local chain without it', async () => {
    mocks.getNetwork.mockResolvedValue({ chainId: 80002n });
    vi.stubEnv('ALLOW_MAINNET_SPEND', 'true');
    await expect(sendVerification(config, verification)).resolves.toMatchObject({ transactionHash: TX_HASH });
    vi.stubEnv('ALLOW_MAINNET_SPEND', '');
    mocks.getNetwork.mockResolvedValue({ chainId: 31337n });
    await expect(sendVerification(config, verification)).resolves.toMatchObject({ transactionHash: TX_HASH });
    expect(mocks.send).toHaveBeenCalledTimes(2);
  });

  it('refuses any other chain too, naming it', async () => {
    mocks.getNetwork.mockResolvedValue({ chainId: 137n });
    await expect(sendVerification(config, verification)).rejects.toThrow('Refusing to spend on chain 137.');
    expect(mocks.send).not.toHaveBeenCalled();
  });
});

describe('Chain submission', () => {
  it.each([
    ['TrancheReleased', ['ATH-0142', 0, 600n, ADDRESS], 'released'],
    ['PaymentHeld', ['ATH-0142', 0, 'Measurement thresholds not met'], 'held'],
    ['ForceMajeureApplied', ['ATH-0142', 0n, 0n], 'force_majeure'],
  ] as const)('returns the receipt outcome for %s', async (name, args, outcome) => {
    mocks.wait.mockResolvedValue({ hash: TX_HASH, blockNumber: 42, status: 1, logs: [eventLog(name, args)] });
    const result = await sendVerification(config, verification);
    expect(result).toMatchObject({ transactionHash: TX_HASH, blockNumber: 42, outcome });
    expect(mocks.send).toHaveBeenCalledWith('ATH-0142', 0, -111n, 94, false, 0, VERIFICATION.evidence_hash, '0x1234', 243n, 0n, verification.measurementId, verification.measuredAt);
    expect(mocks.wait).toHaveBeenCalledWith(1, 120000);
    expect(mocks.destroy).toHaveBeenCalledOnce();
  });

  it('explains insufficient gas funds', async () => {
    mocks.send.mockRejectedValue(makeError('insufficient funds', 'INSUFFICIENT_FUNDS', { transaction: {} }));
    await expect(sendVerification(config, verification)).rejects.toThrow('insufficient native tokens for gas');
    expect(mocks.destroy).toHaveBeenCalledOnce();
  });

  it('decodes a contract custom error into a readable rejection', async () => {
    const data = escrowInterface.encodeErrorResult('PhaseAlreadySettled', ['ATH-0142', 0]);
    mocks.send.mockRejectedValue(makeError('revert', 'CALL_EXCEPTION', {
      action: 'estimateGas', data, transaction: { to: ADDRESS, data: '0x' }, reason: null, invocation: null, revert: null,
    }));
    await expect(sendVerification(config, verification)).rejects.toThrow('PhaseAlreadySettled');
  });

  it('reports an uncertain confirmation with its transaction hash', async () => {
    mocks.wait.mockRejectedValue(new Error('RPC disconnected'));
    await expect(sendVerification(config, verification)).rejects.toThrow(`Transaction: ${TX_HASH}`);
  });

  it('rejects a missing contract and always closes the provider', async () => {
    mocks.getCode.mockResolvedValue('0x');
    await expect(sendVerification(config, verification)).rejects.toThrow('No contract exists');
    expect(mocks.send).not.toHaveBeenCalled();
    expect(mocks.destroy).toHaveBeenCalledOnce();
  });
});
