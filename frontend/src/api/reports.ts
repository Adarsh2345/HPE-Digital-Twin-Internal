import { api } from './client'
import type { TierResult } from './simulation'

export interface HealthReport {
  timestamp: string
  overall_health: 'healthy' | 'warning' | 'critical'
  state_counts: Record<string, number>
  critical_nodes: string[]
  warning_nodes: string[]
  chaos_active: boolean
  tick_count: number
}

export interface ValidateReport {
  timestamp: string
  allowed: boolean
  reasons: string[]
  warnings: string[]
  tier_results: Record<string, TierResult>
}

export interface SummaryReport {
  timestamp: string
  status: Record<string, unknown>
  validation: ValidateReport
  graph: unknown
}

export function getHealth() {
  return api<HealthReport>('GET', '/api/v1/reports/health')
}

export function getValidate() {
  return api<ValidateReport>('GET', '/api/v1/reports/validate')
}

export function getSummary() {
  return api<SummaryReport>('GET', '/api/v1/reports/summary')
}

export function getNodeReport(nodeId: string) {
  return api<unknown>('GET', `/api/v1/reports/node/${encodeURIComponent(nodeId)}`)
}
