import { api, ApiError } from './client'
import type { SimulationResult, TierResult } from './simulation'

export interface ParserMetadata {
  request_text: string
  parser_used: string
  action: string
}

export interface SimulationReport {
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
}

export interface ResolveMetricsResponse {
  parser_metadata: ParserMetadata
  simulation_report: SimulationReport
  clone_id?: string
  projected_graph?: unknown
  projections: Record<string, unknown>[]
  tier_results: Record<string, TierResult>
  scenario_results: { scenario?: string; passed?: boolean; [key: string]: unknown }[]
  impact_predictions: Record<string, unknown>
}

export function resolveMetrics(
  requestText: string,
  override?: { action: string; params: Record<string, unknown> },
) {
  const body = override
    ? { action: override.action, params: override.params, request_text: requestText, parser_used: 'form' }
    : { request_text: requestText }
  return api<ResolveMetricsResponse>('POST', '/api/v1/metrics/resolve', body)
}

export function formatApiError(error: unknown): string {
  if (error instanceof ApiError) {
    const body = error.body as { detail?: unknown } | undefined
    const detail = body?.detail
    if (Array.isArray(detail)) {
      return detail
        .map((item) => {
          if (typeof item === 'object' && item !== null && 'message' in item) {
            return String((item as { message: unknown }).message)
          }
          return String(item)
        })
        .join(' ')
    }
    if (typeof detail === 'string') return detail
    return error.message
  }
  return error instanceof Error ? error.message : 'Request failed'
}

export interface ApiErrorDetailItem {
  code?: string
  path?: string
  message?: string
  value?: string
  details?: { path?: string; message?: string; value?: string }[]
}

/** Extract the structured `detail` array/object from a failed request, if present. */
export function extractApiErrorDetail(error: unknown): ApiErrorDetailItem[] | null {
  if (!(error instanceof ApiError)) return null
  const body = error.body as { detail?: unknown } | undefined
  const detail = body?.detail
  if (Array.isArray(detail)) return detail as ApiErrorDetailItem[]
  if (typeof detail === 'object' && detail !== null) return [detail as ApiErrorDetailItem]
  return null
}

/** Prefer simulate response; fall back to resolve payload for unified display. */
export function mergeSimulationDisplay(
  resolved: ResolveMetricsResponse,
  simulated: SimulationResult | null,
): SimulationResult {
  if (simulated) return simulated
  const report = resolved.simulation_report
  return {
    timestamp: report.timestamp,
    action: report.action,
    params: report.params,
    allowed: report.allowed,
    verdict: report.verdict,
    reasons: report.reasons,
    warnings: report.warnings,
    recommendations: report.recommendations,
    tier_results: resolved.tier_results ?? report.tier_results,
    mutation_summary: report.mutation_summary,
    projection_steps: report.projection_steps,
    clone_id: resolved.clone_id,
    projected_graph: resolved.projected_graph,
    projections: resolved.projections,
    scenario_results: resolved.scenario_results,
    impact_predictions: resolved.impact_predictions,
  }
}
