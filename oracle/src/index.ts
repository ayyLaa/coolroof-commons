import { parseRound, roundRoofId } from '../../contracts/shared/demo-round';
import { fetchDemoRound, fetchVerification } from './backend';
import { sendVerification } from './chain';
import type { SubmissionResult } from './chain';
import { loadConfig } from './config';
import { mapVerification, parsePhase, validateRoofId } from './verification';
import type { Phase } from './verification';
import { FORCE_MAJEURE_STATUS, VERIFICATION_STATUS } from '../../contracts/shared/status';

export interface NotSubmittedResult {
  outcome: 'not_submitted'; reason: string; transactionHash: null; blockNumber: null;
  events: []; tranche: 'QUALITY' | 'DURABILITY';
}
export type OracleResult = SubmissionResult | NotSubmittedResult;

function refusal(status: number, forceMajeure: boolean, phase: Phase): string | null {
  if (forceMajeure) {
    return phase === 'durability' && status === FORCE_MAJEURE_STATUS
      ? null : 'Not submitted: force majeure requires an insufficient_data durability result.';
  }
  if (status === VERIFICATION_STATUS.approved) return null;
  const name = status === VERIFICATION_STATUS.flagged ? 'flagged' : 'insufficient_data';
  return `Not submitted: status is ${name}. No payment was attempted.`;
}

/**
 * The backend knows the roof; the chain knows that round's project ("ATH-0142#3"). With no
 * round given, the backend's current round is used, so the demo panel needs no change.
 */
export async function submitToChain(roofId: string, phase: Phase, round?: number): Promise<OracleResult> {
  validateRoofId(roofId);
  parsePhase(phase);
  const config = loadConfig();
  const chainRound = round === undefined ? await fetchDemoRound(config.backendUrl) : parseRound(round);
  const response = await fetchVerification(config.backendUrl, roofId);
  const verification = { ...mapVerification(response, roofId, phase), roofId: roundRoofId(roofId, chainRound) };
  const reason = refusal(verification.status, verification.forceMajeure, phase);
  if (reason) return {
    outcome: 'not_submitted', reason, transactionHash: null, blockNumber: null, events: [],
    tranche: phase === 'quality' ? 'QUALITY' : 'DURABILITY',
  };
  return sendVerification(config, verification);
}
