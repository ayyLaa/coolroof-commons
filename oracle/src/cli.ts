import { parseArgs } from 'node:util';
import { OracleError, errorMessage } from './errors';
import { submitToChain } from './index';
import { parsePhase } from './verification';

async function main(): Promise<void> {
  let values: { roof?: string; phase?: string; help?: boolean };
  try {
    const parsed = parseArgs({ allowPositionals: true, options: {
      roof: { type: 'string' }, phase: { type: 'string' }, help: { type: 'boolean' },
    } });
    values = parsed.values;
    // Some PowerShell npm shims strip the option names but preserve their values.
    if (parsed.positionals.length === 2 && !values.roof && !values.phase) {
      values = { ...values, roof: parsed.positionals[0], phase: parsed.positionals[1] };
    } else if (parsed.positionals.length) {
      throw new Error('Unexpected positional arguments');
    }
  } catch { throw new OracleError('CLI_USAGE', 'Use: npm run submit -- --roof ATH-0142 --phase quality|durability'); }
  if (values.help) { console.log('Usage: npm run submit -- --roof ATH-0142 --phase quality|durability'); return; }
  if (!values.roof || !values.phase) throw new OracleError('CLI_USAGE', 'Both --roof and --phase are required.');
  const result = await submitToChain(values.roof, parsePhase(values.phase));
  console.log(JSON.stringify(result, null, 2));
}

if (require.main === module) {
  main().catch((error: unknown) => { console.error(errorMessage(error)); process.exitCode = 1; });
}
