const TOKEN_KEY = 'coolroof.operator-token'

export function operatorToken(): string {
  return typeof sessionStorage === 'undefined' ? '' : (sessionStorage.getItem(TOKEN_KEY) ?? '')
}

export function storeOperatorToken(value: string): void {
  if (value) sessionStorage.setItem(TOKEN_KEY, value)
  else sessionStorage.removeItem(TOKEN_KEY)
}
