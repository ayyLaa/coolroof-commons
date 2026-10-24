import { Interface } from 'ethers';

// Keep this minimal ABI aligned with contracts/contracts/CoolRoofEscrow.sol.
export const ESCROW_ABI = [
  'function owner() view returns (address)',
  'function submitVerification(string roofId,uint8 status,int256 normalizedDeltaCx10,uint256 coveragePct,bool forceMajeure,uint8 phase,bytes32 evidenceHash,bytes deviceSignature,uint256 maxGustMsX10,uint256 precipMmX10,bytes32 measurementId,uint256 measuredAt)',
  'event TrancheReleased(string roofId,uint8 tranche,uint256 amount,address indexed to)',
  'event PaymentHeld(string roofId,uint8 tranche,string reason)',
  'event ForceMajeureApplied(string roofId,uint256 maxGustMsX10,uint256 precipMmX10)',
  'event UnreleasedReclaimed(string roofId,address indexed sponsor,uint256 amount)',
  'error UnauthorizedOracle(address caller)', 'error InvalidAddress()', 'error InvalidRoofId()',
  'error InvalidDeposit()', 'error InvalidThresholds()', 'error ProjectAlreadyExists(string roofId)',
  'error ProjectNotFound(string roofId)', 'error InvalidPhase(uint8 phase)',
  'error InvalidCoverage(uint256 coveragePct)', 'error InvalidForceMajeurePhase()',
  'error PhaseAlreadySettled(string roofId,uint8 tranche)', 'error PaymentFailed(address recipient,uint256 amount)',
  'error ReentrancyGuardReentrantCall()', 'error ProjectClosed(string roofId)',
  'error NotProjectSponsor(address caller)', 'error ReclaimNotYetAvailable(uint256 availableAt)',
] as const;
export const escrowInterface = new Interface(ESCROW_ABI);
export const EVENT_NAMES = ['TrancheReleased', 'PaymentHeld', 'ForceMajeureApplied', 'UnreleasedReclaimed'] as const;
