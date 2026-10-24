// CoolRoofEscrow.sol's Tranche enum, in declaration order: the index is the on-chain value.
export const TRANCHE_NAMES = ['QUALITY', 'DURABILITY', 'FORCE_MAJEURE_RESERVE'] as const;
export type TrancheName = typeof TRANCHE_NAMES[number];
export const TRANCHE = { QUALITY: 0, DURABILITY: 1, FORCE_MAJEURE_RESERVE: 2 } as const satisfies Record<TrancheName, number>;
