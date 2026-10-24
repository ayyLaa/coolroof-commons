import { describe, expect, it } from 'vitest'
import { ApiError } from '../../src/api/client'
import { isMissingMeasurementError, isMixedDataSourceError } from '../../src/api/errors'
import { errorCodeOf } from '../../src/hooks/useApiResource'
import { demoErrorMessage } from '../../src/api/demo'
import { significanceLabel } from '../../src/lib/evidence'

describe('Missing measurements', () => {
  const missing = new ApiError(409, {
    code: 'missing_measurement',
    message: "LON-2064 has no 'before' measurement yet.",
  })
  it('reads an unmeasured roof as missing data, not as a failure', () => {
    expect(isMissingMeasurementError(missing)).toBe(true)
    expect(errorCodeOf(missing)).toBe('missing_measurement')
  })
  it('keeps other conflicts and statuses as they are', () => {
    expect(isMissingMeasurementError(new ApiError(409, { code: 'mixed_data_source' }))).toBe(false)
    expect(isMissingMeasurementError(new ApiError(404, { code: 'missing_measurement' }))).toBe(
      false,
    )
    expect(errorCodeOf(new ApiError(409, { code: 'mixed_data_source' }))).toBe('mixed_data_source')
  })
})

describe('Mixed data source errors', () => {
  it.each([
    { code: 'mixed_data_source' },
    { error: 'mixed_data_source' },
    { detail: 'mixed_data_source' },
    { detail: { code: 'mixed_data_source' } },
    { error: { code: 'mixed_data_source' } },
  ])('recognizes a structured 409 response: %j', body => {
    expect(isMixedDataSourceError(new ApiError(409, body))).toBe(true)
  })
  it('does not relabel unrelated conflicts or other status codes', () => {
    expect(isMixedDataSourceError(new ApiError(409, { code: 'project_exists' }))).toBe(false)
    expect(isMixedDataSourceError(new ApiError(400, { code: 'mixed_data_source' }))).toBe(false)
    expect(isMixedDataSourceError(new Error('mixed_data_source'))).toBe(false)
  })
  it('passes the backend mixed-source message through to the demo', () => {
    const body = {
      code: 'mixed_data_source',
      message: 'Cannot compare a measured measurement with the simulated before measurement.',
    }
    expect(demoErrorMessage(new ApiError(409, body), true)).toBe(body.message)
  })
})

describe('Satellite uncertainty', () => {
  it('displays the reported non-significant result without a success claim', () => {
    expect(significanceLabel({ significant: false, p_value: 0.25 })).toBe(
      'Not statistically significant (p = 0.25)',
    )
  })
  it('does not round a small nonzero p-value to zero', () => {
    expect(significanceLabel({ significant: true, p_value: 0.00001 })).toBe(
      'Statistically significant (p = 0.00001)',
    )
  })
  it('uses the supplied significance flag instead of inventing an alpha threshold', () => {
    expect(significanceLabel({ significant: false, p_value: 0.001 })).toContain(
      'Not statistically significant',
    )
    expect(significanceLabel({ significant: null, p_value: 0.25 })).toContain(
      'Significance not supplied',
    )
  })
  it('does not fabricate missing or out-of-range p-values', () => {
    expect(significanceLabel({ significant: false, p_value: null })).toContain('p unavailable')
    expect(significanceLabel({ significant: false, p_value: 2 })).toContain('p unavailable')
  })
})
