import { useState, type ReactNode } from 'react'
import { Loader2, Sparkles, X } from 'lucide-react'
import { PageHeader, Card, ErrorBanner } from '../components/ui'
import {
  resolveMetrics,
  formatApiError,
  mergeSimulationDisplay,
  type ResolveMetricsResponse,
} from '../api/metrics'
import { runSimulation, type SimulationResult } from '../api/simulation'
import {
  formatActionLabel,
  riskFromSimulation,
  severityBadgeClass,
  shortNodeId,
  stateBadgeClass,
} from '../utils/format'

const EXAMPLE_PROMPTS = [
  'move server-1 to router-2',
  'add compute node server-5 to router-1',
  'remove server-4',
  'inject CPU 92% on server-1',
  'latency 160ms spine-router to router-1',
  '3900 iops on server-2',
]

export default function PromptAssistantPage() {
  const [prompt, setPrompt] = useState('')
  const [loading, setLoading] = useState(false)
  const [loadingPhase, setLoadingPhase] = useState<'resolve' | 'simulate' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [resolveResult, setResolveResult] = useState<ResolveMetricsResponse | null>(null)
  const [simResult, setSimResult] = useState<SimulationResult | null>(null)

  const handleClear = () => {
    setPrompt('')
    setError(null)
    setResolveResult(null)
    setSimResult(null)
  }

  const handleSubmit = async () => {
    const text = prompt.trim()
    if (!text) return

    setLoading(true)
    setLoadingPhase('resolve')
    setError(null)
    setResolveResult(null)
    setSimResult(null)

    try {
      const resolved = await resolveMetrics(text)
      setResolveResult(resolved)

      const { action } = resolved.parser_metadata
      const params = resolved.simulation_report?.params

      if (action && params && Object.keys(params).length > 0) {
        setLoadingPhase('simulate')
        const simulated = await runSimulation({
          action,
          params,
          projection_steps: resolved.simulation_report.projection_steps || 3,
        })
        setSimResult(simulated)
      }
    } catch (e) {
      setError(formatApiError(e))
    } finally {
      setLoading(false)
      setLoadingPhase(null)
    }
  }

  const display = resolveResult ? mergeSimulationDisplay(resolveResult, simResult) : null
  const meta = resolveResult?.parser_metadata

  return (
    <div>
      <PageHeader
        title="Prompt Assistant"
        subtitle="Natural language infrastructure commands — parse, simulate, and validate"
      />

      <Card title="User Prompt" className="mb-4">
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Describe an infrastructure change in plain English…"
          rows={4}
          disabled={loading}
          className="w-full bg-surface3 border border-border rounded-lg px-4 py-3 text-sm text-gray-200 placeholder:text-faint focus:outline-none focus:border-accent/50 resize-y min-h-[100px]"
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) handleSubmit()
          }}
        />

        <div className="flex flex-wrap gap-2 mt-3">
          {EXAMPLE_PROMPTS.map((example) => (
            <button
              key={example}
              type="button"
              disabled={loading}
              onClick={() => setPrompt(example)}
              className="text-xs px-3 py-1.5 rounded-full bg-surface3 text-muted border border-border hover:text-accent hover:border-accent/40 transition disabled:opacity-50"
            >
              {example}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-3 mt-4">
          <button
            type="button"
            onClick={handleSubmit}
            disabled={loading || !prompt.trim()}
            className="btn-primary"
          >
            {loading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                {loadingPhase === 'simulate' ? 'Running simulation…' : 'Parsing intent…'}
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4" />
                Submit
              </>
            )}
          </button>
          <button
            type="button"
            onClick={handleClear}
            disabled={loading}
            className="flex items-center gap-1.5 px-4 py-2 text-sm text-muted border border-border rounded-lg hover:text-gray-200 hover:bg-surface2 transition disabled:opacity-50"
          >
            <X className="w-4 h-4" />
            Clear
          </button>
          <span className="text-xs text-faint hidden sm:inline">Ctrl+Enter to submit</span>
        </div>
      </Card>

      {error && (
        <div className="space-y-2 mb-4">
          <ErrorBanner message={error} />
          {error.includes('action name') || error.includes('Could not parse') ? (
            <p className="text-xs text-muted px-1">
              Tip: Use a complete sentence with node names. Click one of the example chips above,
              such as <span className="text-accent">move server-1 to router-2</span>.
            </p>
          ) : null}
        </div>
      )}

      {resolveResult && meta && (
        <div className="space-y-4">
          <Card title="Parsed Action">
            <dl className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
              <Field label="Parser" value={meta.parser_used} />
              <Field label="Action" value={meta.action.replace(/_/g, ' ')} />
              <Field
                label="Resolved Intent"
                value={formatActionLabel(meta.action, resolveResult.simulation_report.params)}
                className="sm:col-span-2"
              />
            </dl>
            <div className="mt-4">
              <p className="text-xs text-muted mb-2">Parameters</p>
              <pre className="text-xs font-mono text-gray-400 bg-surface3 rounded-lg p-3 overflow-x-auto">
                {JSON.stringify(resolveResult.simulation_report.params, null, 2)}
              </pre>
            </div>
          </Card>

          {display && (
            <>
              <Card title="Simulation Summary">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                  <SummaryTile
                    label="Verdict"
                    value={
                      <span className={`badge ${display.allowed ? 'bg-green-500/15 text-green-400' : 'bg-red-500/15 text-red-400'}`}>
                        {display.verdict}
                      </span>
                    }
                  />
                  <SummaryTile
                    label="Risk Level"
                    value={
                      <span className={`badge ${severityBadgeClass(riskFromSimulation(display.allowed, display.reasons, display.warnings))}`}>
                        {riskFromSimulation(display.allowed, display.reasons, display.warnings)}
                      </span>
                    }
                  />
                  <SummaryTile label="Projection Steps" value={String(display.projection_steps)} />
                  <SummaryTile label="Clone ID" value={display.clone_id ?? '—'} mono />
                </div>

                <p className="text-xs text-muted mb-2">Change</p>
                <p className="text-sm text-white font-medium mb-4">
                  {formatActionLabel(display.action, display.params)}
                </p>

                {Object.keys(display.impact_predictions).length > 0 && (
                  <div className="mb-4">
                    <p className="text-xs text-muted mb-2">Impact Analysis</p>
                    <pre className="text-xs font-mono text-gray-400 bg-surface3 rounded-lg p-3 overflow-x-auto max-h-40">
                      {JSON.stringify(display.impact_predictions, null, 2)}
                    </pre>
                  </div>
                )}

                {display.scenario_results.length > 0 && (
                  <div>
                    <p className="text-xs text-muted mb-2">Scenario Results</p>
                    <div className="flex flex-wrap gap-2">
                      {display.scenario_results.map((s, i) => (
                        <span
                          key={i}
                          className={`badge text-xs ${s.passed === false ? 'bg-red-500/15 text-red-400' : 'bg-green-500/15 text-green-400'}`}
                        >
                          {shortNodeId(String(s.scenario ?? s.node_id ?? `scenario-${i}`))}:{' '}
                          {s.passed === false ? 'FAIL' : 'PASS'}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </Card>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <Card title="Recommendations">
                  {display.recommendations.length === 0 && display.warnings.length === 0 && display.reasons.length === 0 ? (
                    <p className="text-sm text-green-400">All constraint tiers cleared — change is safe to apply.</p>
                  ) : (
                    <ul className="space-y-2 text-sm">
                      {display.recommendations.map((rec, i) => (
                        <li key={i} className="text-gray-300 flex gap-2">
                          <span className="text-accent flex-shrink-0">→</span>
                          {rec}
                        </li>
                      ))}
                      {display.recommendations.length === 0 && display.allowed && (
                        <li className="text-gray-400">No remediation required.</li>
                      )}
                    </ul>
                  )}

                  {display.warnings.length > 0 && (
                    <div className="mt-4 pt-4 border-t border-border">
                      <p className="text-xs text-muted mb-2">Warnings</p>
                      <ul className="space-y-1.5">
                        {display.warnings.map((w, i) => (
                          <li key={i} className="text-xs text-yellow-300/90">
                            {w}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {display.reasons.length > 0 && (
                    <div className="mt-4 pt-4 border-t border-border">
                      <p className="text-xs text-muted mb-2">Violations</p>
                      <ul className="space-y-1.5">
                        {display.reasons.map((r, i) => (
                          <li key={i} className="text-xs text-red-300">
                            {r}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </Card>

                <Card title="Validation Status">
                  <div className="flex items-center gap-2 mb-4">
                    <span className={`badge capitalize ${stateBadgeClass(display.allowed ? 'healthy' : 'critical')}`}>
                      {display.allowed ? 'Allowed' : 'Blocked'}
                    </span>
                    <span className="text-xs text-muted">
                      {display.reasons.length} violation{display.reasons.length !== 1 ? 's' : ''},{' '}
                      {display.warnings.length} warning{display.warnings.length !== 1 ? 's' : ''}
                    </span>
                  </div>

                  {Object.keys(display.tier_results).length > 0 ? (
                    <div className="space-y-2">
                      {Object.entries(display.tier_results).map(([tier, tr]) => (
                        <div
                          key={tier}
                          className="flex items-center justify-between px-3 py-2 rounded-lg bg-surface3 text-sm"
                        >
                          <span className="text-gray-300 capitalize">{tier}</span>
                          <span
                            className={`badge text-xs ${tr.passed === false ? 'bg-red-500/15 text-red-400' : 'bg-green-500/15 text-green-400'}`}
                          >
                            {tr.passed === false ? 'FAIL' : 'PASS'}
                          </span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-muted">No tier validation data returned.</p>
                  )}
                </Card>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}

function Field({
  label,
  value,
  className = '',
}: {
  label: string
  value: string
  className?: string
}) {
  return (
    <div className={className}>
      <dt className="text-muted text-xs mb-0.5">{label}</dt>
      <dd className="text-white font-medium capitalize">{value}</dd>
    </div>
  )
}

function SummaryTile({
  label,
  value,
  mono = false,
}: {
  label: string
  value: ReactNode
  mono?: boolean
}) {
  return (
    <div>
      <p className="text-xs text-muted mb-0.5">{label}</p>
      <div className={`text-sm font-medium text-white ${mono ? 'font-mono text-xs truncate' : ''}`}>
        {value}
      </div>
    </div>
  )
}
