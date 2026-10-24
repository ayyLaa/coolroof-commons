import Ajv2020 from 'ajv/dist/2020'
import addFormats from 'ajv-formats'
import { load } from 'js-yaml'
import { describe, expect, it } from 'vitest'
import openapiText from '../../../openapi.yaml?raw'
import verificationText from '../../../schema/verification.json?raw'
import satellite from '../../../data/snapshots/satellite_evidence.json'
import climate from '../../../data/snapshots/climate_comparison.json'
import metrics from '../../../data/snapshots/metrics.json'

// The frontend types are generated from openapi.yaml, so a field the backend sends but the
// contract omits (or the reverse) would otherwise surface only as undefined at runtime.
// These are the committed reports the backend serves; each must fit its closed schema.
const BASE = 'http://contract.local/'
const openapi = load(openapiText) as {
  paths: Record<string, { get: { responses: Record<string, ExampleResponse> } }>
}
interface ExampleResponse {
  content: { 'application/json': { example: unknown } }
}

const ajv = new Ajv2020({ strict: false, allErrors: true })
addFormats(ajv)
ajv.addSchema({ ...(openapi as object), $id: `${BASE}openapi.yaml` })
ajv.addSchema({ ...JSON.parse(verificationText), $id: `${BASE}schema/verification.json` })

function errorsFor(schema: string, data: unknown): string[] {
  const validate = ajv.getSchema(`${BASE}openapi.yaml#/components/schemas/${schema}`)
  if (!validate) throw new Error(`No schema ${schema} in openapi.yaml`)
  return validate(data)
    ? []
    : (validate.errors ?? []).map(error => `${error.instancePath || '/'} ${error.message}`)
}

function exampleOf(path: string): unknown {
  return openapi.paths[path].get.responses['200'].content['application/json'].example
}

const REPORTS = [
  { schema: 'SatelliteEvidence', path: '/evidence/satellite', report: satellite },
  { schema: 'ClimateComparison', path: '/evidence/climate-comparison', report: climate },
  { schema: 'MetricsReport', path: '/metrics', report: metrics },
]

describe('Evidence contract', () => {
  for (const { schema, path, report } of REPORTS) {
    it(`${schema}: the served report fits the closed schema`, () => {
      expect(errorsFor(schema, report)).toEqual([])
    })
    it(`${schema}: the openapi.yaml example fits the closed schema`, () => {
      expect(errorsFor(schema, exampleOf(path))).toEqual([])
    })
  }
  it('rejects a field the contract does not name, however deep', () => {
    const renamed = structuredClone(metrics) as { normalization: { raw_delta: object } }
    renamed.normalization.raw_delta = { ...renamed.normalization.raw_delta, rangeC: 19.1 }
    expect(errorsFor('MetricsReport', renamed)).toContain(
      '/normalization/raw_delta must NOT have unevaluated properties',
    )
  })
})
