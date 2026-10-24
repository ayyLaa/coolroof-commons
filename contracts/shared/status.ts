// The backend status codes and the separate on-chain weather exception must agree
// with CoolRoofEscrow's named constants; contract tests enforce the mapping.
export const VERIFICATION_STATUS = { approved: 0, flagged: 1, insufficient_data: 2 } as const;
export const FORCE_MAJEURE_STATUS = 3;

export type VerificationStatusName = keyof typeof VERIFICATION_STATUS;
