import type { Log } from 'ethers';
import { escrowInterface } from './abi';

export interface ChainEvent {
  event: 'TrancheReleased' | 'PaymentHeld' | 'ForceMajeureApplied' | 'UnreleasedReclaimed';
  roofId: string; transactionHash: string; blockNumber: number; blockHash: string;
  logIndex: number; removed: boolean; eventId: string;
  data: Record<string, string | number>;
}

export type EventLog = Pick<Log, 'topics' | 'data' | 'address' | 'transactionHash' | 'blockNumber' | 'blockHash' | 'index' | 'removed'>;

export function decodeEvent(log: EventLog): ChainEvent | null {
  const parsed = escrowInterface.parseLog({ topics: [...log.topics], data: log.data });
  if (!parsed) return null;
  let data: ChainEvent['data'];
  switch (parsed.name) {
    case 'TrancheReleased':
      data = { tranche: Number(parsed.args.tranche), amount: parsed.args.amount.toString(), to: String(parsed.args.to) };
      break;
    case 'PaymentHeld':
      data = { tranche: Number(parsed.args.tranche), reason: String(parsed.args.reason) };
      break;
    case 'UnreleasedReclaimed':
      data = { amount: parsed.args.amount.toString(), sponsor: String(parsed.args.sponsor) };
      break;
    case 'ForceMajeureApplied':
      data = { maxGustMsX10: parsed.args.maxGustMsX10.toString(), precipMmX10: parsed.args.precipMmX10.toString() };
      break;
    default: return null;
  }
  return {
    event: parsed.name as ChainEvent['event'], roofId: String(parsed.args.roofId), data,
    transactionHash: log.transactionHash, blockNumber: log.blockNumber, blockHash: log.blockHash,
    logIndex: log.index, removed: log.removed, eventId: `${log.blockHash}:${log.transactionHash}:${log.index}`,
  };
}
