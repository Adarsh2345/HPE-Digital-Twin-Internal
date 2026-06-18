import { api } from './client'

export interface NodeTelemetry {
  state: string
  metrics: Record<string, number | string | boolean>
}

export interface TelemetrySnapshot {
  nodes: Record<string, NodeTelemetry>
  edges: Record<string, { state: string; metrics: Record<string, number | string | boolean> }>
  chaos_active: boolean
  tick_count: number
}

export interface NodeTelemetryDetail {
  node_id: string
  state: string
  metrics: Record<string, number | string | boolean>
  rolling_avg_cpu?: number
  anomaly_detected?: boolean
  history_count: number
  recent_history: unknown[]
}

export interface OrchestratorStatus {
  tick_count: number
  last_tick?: string
  chaos: { active: boolean; scenario?: string; affected_nodes?: string[] }
  nodes: number
  edges: number
  redis_connected: boolean
  neo4j_connected: boolean
  influx_connected: boolean
}

export function getTelemetry() {
  return api<TelemetrySnapshot>('GET', '/api/v1/telemetry')
}

export function getNodeTelemetry(nodeId: string) {
  return api<NodeTelemetryDetail>('GET', `/api/v1/telemetry/${encodeURIComponent(nodeId)}`)
}

export function getStatus() {
  return api<OrchestratorStatus>('GET', '/api/v1/telemetry/status')
}
