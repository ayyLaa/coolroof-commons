// Aliases over src/api/schema.d.ts, which `npm run gen:types` generates from the root
// openapi.yaml. Never declare fields here: regenerate instead, so the types cannot drift
// from the backend again.
import type { components, paths } from './schema'

type Schemas = components['schemas']
type JsonOk<Path extends keyof paths, Method extends 'get' | 'post'> =
  NonNullable<paths[Path][Method]> extends { responses: infer R }
    ? R extends { 200: { content: { 'application/json': infer Body } } }
      ? Body
      : R extends { 201: { content: { 'application/json': infer Body } } }
        ? Body
        : never
    : never

export type ApiResponse = unknown
export type ApiErrorBody = Schemas['Error']
export type DataSource = Schemas['DataSource']

export type Roof = Schemas['RoofSummary']
export type RoofDetail = Schemas['RoofDetail']
export type RoofGeometry = Schemas['GeoJsonPolygon']
export type RoofClass = Schemas['RoofClass']
export type RoofListResponse = JsonOk<'/roofs', 'get'>
export type MeasurementHistoryEntry = Schemas['MeasurementHistoryEntry']

export type TemperatureSeries = Schemas['SimulatedSeries']
export type SimulatedPhase = Schemas['SimulatedPhase']

export type MeasurementPhase = Schemas['MeasurementPhase']
export type MeasurementReading = Schemas['Reading']
export type MeasurementCreateRequest = Schemas['MeasurementCreateRequest']
export type MeasurementCreateResponse = Schemas['MeasurementCreateResponse']
export type PhotoUploadResponse = Schemas['PhotoUploadResponse']

// The response schema is schema/verification.json itself; the generator turns that file's
// $defs section into a required property, which no response carries.
export type Verification = Omit<JsonOk<'/verification/{roof_id}', 'get'>, '$defs'>
export type VerificationStatus = Verification['status']

export type Weather = Schemas['WeatherPoint']
export type WeatherSeries = JsonOk<'/weather/{roof_id}', 'get'>

export type TrancheName = Schemas['TrancheName']
export type TrancheState = Schemas['TrancheStatus']
export type TrancheRecord = Schemas['Tranche']
export type ContractThresholds = Schemas['ContractThresholds']
export type ContractEvent = Schemas['ContractEventRecord']
export type ContractEventName = Schemas['ContractEventName']
export type ContractStatus = Schemas['ContractStatus']

export type SatelliteCase = Schemas['SatelliteCase']
export type SatelliteConclusion = Schemas['SatelliteConclusion']
export type SatelliteEvidence = Schemas['SatelliteEvidence']

export type ClimateCity = Schemas['CityClimate']
export type ClimateMethod = Schemas['ClimateMethod']
export type SeasonalBalance = Schemas['SeasonalBalance']
export type ClimateComparison = Schemas['ClimateComparison']

export type MetricsReport = Schemas['MetricsReport']
export type DemoResetResponse = Schemas['DemoResetResponse']
export type DemoRoundStatus = Schemas['DemoRoundStatus']
export type OracleHealth = Schemas['OracleHealth']
