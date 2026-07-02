import { useMemo } from 'react'
import { Server, Zap, ShieldAlert, Cpu, Thermometer, HardDrive, Activity } from 'lucide-react'
import { PageHeader, LoadingSpinner, ErrorBanner } from '../components/ui'
import { usePolling } from '../hooks/usePolling'
import { getTelemetry, type NodeTelemetry } from '../api/telemetry'
import {
  aggregatePowerKw,
  averageCpu,
  formatNumber,
  shortNodeId,
  stateBadgeClass,
} from '../utils/format'

type NodeEntry = [string, NodeTelemetry]

const METRIC_KEYS = [
  'cpu_percent',
  'memory_percent',
  'power_watts',
  'temperature_celsius',
  'temp_c',
  'disk_iops',
] as const

function hasMetricData(metrics: Record<string, number | string | boolean>): boolean {
  return METRIC_KEYS.some((key) => typeof metrics[key] === 'number')
}

function metricNum(
  metrics: Record<string, number | string | boolean>,
  key: string,
  altKey?: string,
): number | null {
  const value = metrics[key] ?? (altKey ? metrics[altKey] : undefined)
  return typeof value === 'number' ? value : null
}

function temperature(metrics: Record<string, number | string | boolean>): number | null {
  return metricNum(metrics, 'temperature_celsius') ?? metricNum(metrics, 'temp_c')
}

function averageMetric(
  entries: NodeEntry[],
  pick: (metrics: Record<string, number | string | boolean>) => number | null,
): number | null {
  let total = 0
  let count = 0
  for (const [, node] of entries) {
    const value = pick(node.metrics)
    if (value !== null) { total += value; count++ }
  }
  return count > 0 ? total / count : null
}

function sumMetric(
  entries: NodeEntry[],
  pick: (metrics: Record<string, number | string | boolean>) => number | null,
): number | null {
  let total = 0
  let count = 0
  for (const [, node] of entries) {
    const value = pick(node.metrics)
    if (value !== null) { total += value; count++ }
  }
  return count > 0 ? total : null
}

function topConsumer(
  entries: NodeEntry[],
  pick: (metrics: Record<string, number | string | boolean>) => number | null,
): { id: string; value: number } | null {
  let best: { id: string; value: number } | null = null
  for (const [id, node] of entries) {
    const value = pick(node.metrics)
    if (value === null) continue
    if (!best || value > best.value) best = { id, value }
  }
  return best
}

function MiniBar({ value, max = 100, color = 'bg-accent', barColor }: { value: number; max?: number; color?: string; barColor?: string }) {
  const resolvedColor = barColor ?? color
  const pct = Math.min(100, (value / max) * 100)
  return (
    <div className="h-1 w-full bg-border rounded-full overflow-hidden mt-1.5">
      <div className={`h-full ${resolvedColor} rounded-full transition-all`} style={{ width: `${pct}%` }} />
    </div>
  )
}

function StatTile({
  label,
  value,
  sub,
  icon: Icon,
  iconColor,
  bar,
  barColor,
}: {
  label: string
  value: string
  sub?: string
  icon: React.ElementType
  iconColor: string
  bar?: number
  barColor?: string
}) {
  return (
    <div className="card p-5">
      <div className="flex items-start justify-between mb-3">
        <p className="text-xs font-medium text-muted uppercase tracking-wider">{label}</p>
        <div className="p-1.5 rounded-md bg-surface3">
          <Icon className="w-3.5 h-3.5" style={{ color: iconColor }} />
        </div>
      </div>
      <p className="text-2xl font-bold text-white tracking-tight">{value}</p>
      {sub && <p className="text-xs text-muted mt-1">{sub}</p>}
      {bar !== undefined && (
        <MiniBar value={bar} barColor={barColor} />
      )}
    </div>
  )
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[10px] font-semibold uppercase tracking-widest text-muted mb-3">{children}</p>
  )
}

function KvRow({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-border/50 last:border-0">
      <span className="text-xs text-muted">{label}</span>
      <span className={`text-xs font-semibold ${accent ? 'text-accent' : 'text-white'}`}>{value}</span>
    </div>
  )
}

export default function Dashboard() {
  const telemetry = usePolling(getTelemetry, 4000)

  const data = useMemo(() => {
    if (!telemetry.data) return null

    const { nodes, edges, chaos_active, tick_count } = telemetry.data
    const allEntries = Object.entries(nodes) as NodeEntry[]
    const metricEntries = allEntries.filter(([, n]) => hasMetricData(n.metrics))

    const serverCount = allEntries.filter(([id]) => /server-\d+$/i.test(id)).length
    const alertCount = allEntries.filter(([, n]) => n.state === 'warning' || n.state === 'critical').length
    const criticalCount = allEntries.filter(([, n]) => n.state === 'critical').length
    const healthyCount = allEntries.filter(([, n]) => n.state === 'healthy').length

    const powerKw = aggregatePowerKw(nodes)
    const cpuAvg = averageCpu(nodes)
    const memAvg = averageMetric(metricEntries, (m) => metricNum(m, 'memory_percent'))
    const tempAvg = averageMetric(metricEntries, temperature)
    const totalPowerW = sumMetric(metricEntries, (m) => metricNum(m, 'power_watts'))
    const totalIops = sumMetric(metricEntries, (m) => metricNum(m, 'disk_iops'))

    const topCpu = topConsumer(metricEntries, (m) => metricNum(m, 'cpu_percent'))
    const topMem = topConsumer(metricEntries, (m) => metricNum(m, 'memory_percent'))
    const topPower = topConsumer(metricEntries, (m) => metricNum(m, 'power_watts'))
    const topTemp = topConsumer(metricEntries, temperature)

    const healthLabel = alertCount === 0 ? 'All systems nominal' : criticalCount > 0 ? `${criticalCount} critical` : `${alertCount} warnings`

    const tableRows = metricEntries
      .map(([id, node]) => ({
        id,
        name: shortNodeId(id),
        role: String(node.metrics.role ?? '—'),
        state: node.state,
        cpu: metricNum(node.metrics, 'cpu_percent'),
        memory: metricNum(node.metrics, 'memory_percent'),
        power: metricNum(node.metrics, 'power_watts'),
        temp: temperature(node.metrics),
      }))
      .sort((a, b) => a.name.localeCompare(b.name))

    return {
      servers: String(serverCount),
      power: powerKw !== null ? `${formatNumber(powerKw, 1)} kW` : '—',
      drift: String(alertCount),
      cpu: cpuAvg !== null ? `${formatNumber(cpuAvg, 1)}%` : '—',
      cpuRaw: cpuAvg ?? 0,
      memRaw: memAvg ?? 0,
      driftColor: criticalCount > 0 ? 'text-red-400' : alertCount > 0 ? 'text-yellow-400' : 'text-accent',
      healthLabel,
      overview: {
        totalNodes: allEntries.length,
        totalEdges: Object.keys(edges).length,
        healthyNodes: healthyCount,
        nodesWithMetrics: metricEntries.length,
        chaos: chaos_active ? 'Active' : 'Inactive',
        tickCount: tick_count,
      },
      resources: {
        cpu: cpuAvg !== null ? `${formatNumber(cpuAvg, 1)}%` : '—',
        memory: memAvg !== null ? `${formatNumber(memAvg, 1)}%` : '—',
        temperature: tempAvg !== null ? `${formatNumber(tempAvg, 1)}°C` : '—',
        power: totalPowerW !== null ? `${formatNumber(totalPowerW, 0)} W` : '—',
        iops: totalIops !== null ? formatNumber(totalIops, 0) : '—',
      },
      consumers: {
        cpu: topCpu ? { id: topCpu.id, value: `${formatNumber(topCpu.value, 1)}%` } : null,
        memory: topMem ? { id: topMem.id, value: `${formatNumber(topMem.value, 1)}%` } : null,
        power: topPower ? { id: topPower.id, value: `${formatNumber(topPower.value, 0)} W` } : null,
        temperature: topTemp ? { id: topTemp.id, value: `${formatNumber(topTemp.value, 1)}°C` } : null,
      },
      tableRows,
    }
  }, [telemetry.data])

  return (
    <div>
      <PageHeader
        title="Infrastructure Overview"
        subtitle="Real-time health and capacity metrics across all nodes"
      />

      {telemetry.error && <ErrorBanner message={`Backend unavailable: ${telemetry.error}`} />}

      {telemetry.loading && !data ? (
        <LoadingSpinner label="Fetching live metrics..." />
      ) : data ? (
        <div className="space-y-6">

          {/* ── KPI row ── */}
          <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
            <StatTile label="Active Servers" value={data.servers} sub="Compute nodes in telemetry" icon={Server} iconColor="#4d9fff" />
            <StatTile label="CPU Utilization" value={data.cpu} sub={data.healthLabel} icon={Cpu} iconColor="#a78bfa" bar={data.cpuRaw} barColor="bg-violet-400" />
            <StatTile label="Power Usage" value={data.power} sub="Live aggregate" icon={Zap} iconColor="#00d4aa" />
            <StatTile label="Drift Alerts" value={data.drift} sub={data.healthLabel} icon={ShieldAlert} iconColor="#f87171" />
          </div>

          {/* ── Overview + Resources ── */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div className="card p-5">
              <SectionLabel>Topology snapshot</SectionLabel>
              <KvRow label="Total nodes" value={String(data.overview.totalNodes)} />
              <KvRow label="Connections" value={String(data.overview.totalEdges)} />
              <KvRow label="Healthy nodes" value={String(data.overview.healthyNodes)} accent />
              <KvRow label="Reporting metrics" value={String(data.overview.nodesWithMetrics)} />
              <KvRow label="Chaos injection" value={data.overview.chaos} />
              <KvRow label="Tick count" value={String(data.overview.tickCount)} />
            </div>

            <div className="card p-5">
              <SectionLabel>Resource averages</SectionLabel>
              <div className="space-y-3">
                {[
                  { label: 'CPU', value: data.resources.cpu, raw: data.cpuRaw, icon: Cpu, color: 'bg-violet-400' },
                  { label: 'Memory', value: data.resources.memory, raw: data.memRaw, icon: Activity, color: 'bg-blue-400' },
                ].map(({ label, value, raw, icon: Icon, color }) => (
                  <div key={label}>
                    <div className="flex justify-between items-center mb-1">
                      <span className="text-xs text-muted flex items-center gap-1.5">
                        <Icon className="w-3 h-3" />
                        {label}
                      </span>
                      <span className="text-xs font-semibold text-white">{value}</span>
                    </div>
                    <MiniBar value={raw} barColor={color} />
                  </div>
                ))}
                <div className="pt-2 space-y-0">
                  <KvRow label="Temperature" value={data.resources.temperature} />
                  <KvRow label="Total power" value={data.resources.power} />
                  <KvRow label="Disk IOPS" value={data.resources.iops} />
                </div>
              </div>
            </div>

            <div className="card p-5">
              <SectionLabel>Top consumers</SectionLabel>
              <div className="space-y-3">
                {[
                  { label: 'CPU', icon: Cpu, data: data.consumers.cpu },
                  { label: 'Memory', icon: Activity, data: data.consumers.memory },
                  { label: 'Power', icon: Zap, data: data.consumers.power },
                  { label: 'Temperature', icon: Thermometer, data: data.consumers.temperature },
                ].map(({ label, icon: Icon, data: c }) => (
                  <div key={label} className="flex items-center justify-between">
                    <span className="text-xs text-muted flex items-center gap-1.5">
                      <Icon className="w-3 h-3" />
                      {label}
                    </span>
                    {c ? (
                      <div className="text-right">
                        <span className="text-xs font-medium text-white">{shortNodeId(c.id)}</span>
                        <span className="text-xs text-accent ml-2">{c.value}</span>
                      </div>
                    ) : (
                      <span className="text-xs text-muted">—</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* ── Node table ── */}
          <div className="card">
            <div className="flex items-center justify-between px-5 pt-5 pb-4">
              <div>
                <p className="text-sm font-semibold text-white">Node Metrics</p>
                <p className="text-xs text-muted mt-0.5">{data.tableRows.length} nodes reporting</p>
              </div>
              <div className="flex items-center gap-1.5">
                <HardDrive className="w-3.5 h-3.5 text-muted" />
                <span className="text-xs text-muted">Live</span>
                <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
              </div>
            </div>
            {data.tableRows.length === 0 ? (
              <p className="px-5 pb-5 text-sm text-muted">No nodes with metric data available.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-t border-border">
                      <th className="table-head">Node</th>
                      <th className="table-head">Role</th>
                      <th className="table-head">State</th>
                      <th className="table-head">CPU</th>
                      <th className="table-head">Memory</th>
                      <th className="table-head">Power</th>
                      <th className="table-head">Temp</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.tableRows.map((row) => (
                      <tr key={row.id} className="hover:bg-surface3/40 transition">
                        <td className="table-cell font-medium text-white font-mono text-xs">{row.name}</td>
                        <td className="table-cell text-gray-400 capitalize text-xs">{row.role.replace(/-/g, ' ')}</td>
                        <td className="table-cell">
                          <span className={`badge capitalize ${stateBadgeClass(row.state)}`}>{row.state}</span>
                        </td>
                        <td className="table-cell">
                          {row.cpu !== null ? (
                            <span className={row.cpu >= 80 ? 'text-red-400 text-xs font-semibold' : 'text-gray-400 text-xs'}>
                              {formatNumber(row.cpu, 1)}%
                            </span>
                          ) : <span className="text-muted text-xs">—</span>}
                        </td>
                        <td className="table-cell">
                          {row.memory !== null ? (
                            <span className={row.memory >= 85 ? 'text-yellow-400 text-xs font-semibold' : 'text-gray-400 text-xs'}>
                              {formatNumber(row.memory, 1)}%
                            </span>
                          ) : <span className="text-muted text-xs">—</span>}
                        </td>
                        <td className="table-cell text-gray-400 text-xs">
                          {row.power !== null ? `${formatNumber(row.power, 0)} W` : '—'}
                        </td>
                        <td className="table-cell text-gray-400 text-xs">
                          {row.temp !== null ? `${formatNumber(row.temp, 1)}°C` : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

        </div>
      ) : null}
    </div>
  )
}
