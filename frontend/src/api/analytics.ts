import { api } from './client'

export interface ProfilesResponse {
  ready: boolean
  node_profiles: Record<string, Record<string, unknown>>
  edge_profiles: Record<string, Record<string, unknown>>
}

export interface ScenariosResponse {
  scenarios: Record<string, unknown>[]
  best_k: number
  source: string
}

export interface AnomalyStatus {
  trained: boolean
  if_devices: string[]
  rf_devices: string[]
  model_path?: string
}

export interface AnomalyDetectResult {
  node_id: string
  alert_level: string
  triggers: string[]
  threshold?: Record<string, unknown>
  anomaly?: { score?: number; [key: string]: unknown }
  recommendations: string[]
}

export function getProfiles() {
  return api<ProfilesResponse>('GET', '/api/v1/analytics/profiles')
}

export function getScenarios() {
  return api<ScenariosResponse>('GET', '/api/v1/analytics/scenarios')
}

export function getProfile(nodeId: string) {
  return api<Record<string, unknown>>('GET', `/api/v1/analytics/profile/${encodeURIComponent(nodeId)}`)
}

export function getCorrelations(nodeId: string) {
  return api<{ node_id: string; correlations: Record<string, unknown> }>(
    'GET',
    `/api/v1/analytics/correlations/${encodeURIComponent(nodeId)}`,
  )
}

export function getAnomalyStatus() {
  return api<AnomalyStatus>('GET', '/api/v1/analytics/anomaly/status')
}

export function detectAnomaly(nodeId: string, metrics: Record<string, number>) {
  return api<AnomalyDetectResult>(
    'POST',
    `/api/v1/analytics/anomaly/detect/${encodeURIComponent(nodeId)}`,
    { metrics },
  )
}
