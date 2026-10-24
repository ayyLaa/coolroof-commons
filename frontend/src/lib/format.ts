export function number(value: number | null | undefined, digits = 1): string {
  return value == null || !Number.isFinite(value)
    ? 'Unavailable'
    : new Intl.NumberFormat('en-GB', { maximumFractionDigits: digits }).format(value)
}
export function euro(value: number): string {
  return new Intl.NumberFormat('en-GB', {
    style: 'currency',
    currency: 'EUR',
    maximumFractionDigits: 0,
  }).format(value)
}
export function temperature(value: number | null): string {
  return value == null ? 'Unavailable' : `${number(value)} °C`
}
export function shorten(value: string): string {
  return value.length > 28 ? `${value.slice(0, 16)}…${value.slice(-10)}` : value
}

/** A one-day range (UTC) around a timestamp, the shape GET /weather asks for. */
export function measurementDay(
  timestamp: string | null | undefined,
): { start: string; end: string } | null {
  if (!timestamp) return null
  const day = new Date(timestamp)
  if (Number.isNaN(day.getTime())) return null
  const iso = day.toISOString().slice(0, 10)
  return { start: iso, end: iso }
}
