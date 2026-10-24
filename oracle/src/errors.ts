export class OracleError extends Error {
  constructor(public readonly code: string, message: string) {
    super(message);
    this.name = 'OracleError';
  }
}

export function errorMessage(error: unknown): string {
  return error instanceof OracleError ? error.message : 'Unexpected oracle error. Check configuration and service connectivity.';
}
