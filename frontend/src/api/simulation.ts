import { api } from './client'

export interface SimulationAction {
  category: string
  action: string
  description: string
  params: Record<string, string>
  example: Record<string, unknown>
  constraints_checked: string[]
}

export interface SimulationRequest {
  action: string
  params: Record<string, unknown>
  projection_steps?: number
}

export interface TierResult {
  passed?: boolean
  violations?: string[]
  warnings?: string[]
  future_violations?: string[]
}

export interface SimulationResult {
  timestamp: string
  action: string
  params: Record<string, unknown>
  allowed: boolean
  verdict: string
  reasons: string[]
  warnings: string[]
  recommendations: string[]
  tier_results: Record<string, TierResult>
  mutation_summary?: Record<string, unknown>
  projection_steps: number
  clone_id?: string
  projected_graph?: unknown
  projections: Record<string, unknown>[]
  scenario_results: { scenario?: string; passed?: boolean; [key: string]: unknown }[]
  impact_predictions: Record<string, unknown>
}

export function getActions() {
  return api<{ actions: SimulationAction[] }>('GET', '/api/v1/simulate/actions')
}

export function runSimulation(body: SimulationRequest) {
  return api<SimulationResult>('POST', '/api/v1/simulate', body)
}
