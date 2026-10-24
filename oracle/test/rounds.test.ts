import { describe, expect, it } from 'vitest';
import { parseRound, roundRoofId, splitRoundRoofId } from '../../contracts/shared/demo-round';
import { oracleRoundCostWei, roundsLeft, sponsorRoundCostWei, tokensToWei } from '../../contracts/shared/round-cost';
import { networkName, spendRefusal } from '../../contracts/shared/spend-guard';

const GWEI = 1_000_000_000n;

describe('Demo round keys', () => {
  it('keeps round 0 unsuffixed and suffixes later rounds', () => {
    expect(roundRoofId('ATH-0142', 0)).toBe('ATH-0142');
    expect(roundRoofId('ATH-0142', 3)).toBe('ATH-0142#3');
  });

  it('splits a chain key back into the roof and its round', () => {
    expect(splitRoundRoofId('ATH-0142#3')).toEqual({ roofId: 'ATH-0142', round: 3 });
    expect(splitRoundRoofId('ATH-0142')).toEqual({ roofId: 'ATH-0142', round: 0 });
    // Not a round suffix: a roof ID may contain "#" followed by something else.
    expect(splitRoundRoofId('roof#a')).toEqual({ roofId: 'roof#a', round: 0 });
  });

  it.each([-1, 1.5, 'x', '', null])('rejects %s as a round', value => {
    expect(() => parseRound(value)).toThrow('round must be a whole number');
  });

  it('accepts a round given as digits, as a shell passes it', () => {
    expect(parseRound('12')).toBe(12);
  });
});

describe('Spend guard rules', () => {
  it('names the network a chain id belongs to', () => {
    expect([networkName(31337n), networkName(80002n), networkName(137n)]).toEqual(['local', 'amoy', 'other']);
  });

  it.each([
    [31337n, undefined, null],
    [80002n, undefined, 'Refusing to spend real POL on Amoy. Set ALLOW_MAINNET_SPEND=true to proceed.'],
    [80002n, 'yes', 'Refusing to spend real POL on Amoy. Set ALLOW_MAINNET_SPEND=true to proceed.'],
    [80002n, 'TRUE', null],
  ])('chain %s with flag %s', (chainId, flag, expected) => {
    expect(spendRefusal(chainId, flag)).toBe(expected);
  });
});

describe('Token amounts', () => {
  it('converts the demo deposit to wei like ethers.parseEther', () => {
    expect(tokensToWei('0.001')).toBe(1_000_000_000_000_000n);
    expect(tokensToWei('2')).toBe(2_000_000_000_000_000_000n);
  });

  it.each(['', 'x', '1.2.3', '-1', `0.${'1'.repeat(19)}`])('rejects %s', value => {
    expect(() => tokensToWei(value)).toThrow('Not a token amount');
  });
});

describe('Round budget', () => {
  it('charges the sponsor three deposits and three createProject calls a round', () => {
    // 3 x (0.001 POL + 253,000 gas x 30 gwei)
    expect(sponsorRoundCostWei(30n * GWEI)).toBe(25_770_000_000_000_000n);
  });

  it('charges the oracle the setup quality payment plus one submission per roof', () => {
    expect(oracleRoundCostWei(30n * GWEI)).toBe(4n * 195_000n * 30n * GWEI);
  });

  it('counts whole rounds only, and none when nothing is affordable', () => {
    expect(roundsLeft(54_000_000_000_000_000n, 25_770_000_000_000_000n)).toBe(2);
    expect(roundsLeft(1n, 25_770_000_000_000_000n)).toBe(0);
    expect(roundsLeft(1n, 0n)).toBe(0);
  });
});
