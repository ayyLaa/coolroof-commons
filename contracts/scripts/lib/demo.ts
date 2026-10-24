import { VERIFICATION_STATUS } from '../../shared/status';
import { escrowThresholds } from './thresholds';

export { DEMO_DEPOSIT, DEMO_ROOF_IDS } from '../../shared/demo-round';
// The demo roofs are in Athens.
export const DEMO_THRESHOLDS = escrowThresholds('athens');
export const APPROVED_STATUS = VERIFICATION_STATUS.approved;
export { TRANCHE } from '../../shared/tranche';
// The same roof IDs as the backend seed, the oracle and the demo panel.
export const DEMO_PROJECTS = [
  { roofId: 'ATH-0142', label: 'Successful intervention', normalizedDeltaCx10: -111, coveragePct: 94 },
  { roofId: 'ATH-0287', label: 'Poor coating', normalizedDeltaCx10: -32, coveragePct: 41 },
  { roofId: 'ATH-0355', label: 'Storm scenario', normalizedDeltaCx10: -111, coveragePct: 94 },
] as const;
// The storm demo starts at the durability recheck, which the escrow only accepts once
// the quality tranche has been paid; setup-demo pays it for these roofs.
export const QUALITY_PAID_AT_SETUP: readonly string[] = ['ATH-0355'];
