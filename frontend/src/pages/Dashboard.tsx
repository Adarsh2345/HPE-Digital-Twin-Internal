import { useMemo } from 'react'
import { Server, Zap, ShieldAlert, Cpu } from 'lucide-react'
import MetricCard from '../components/MetricCard'
import { PageHeader, Card, LoadingSpinner, ErrorBanner } from '../components/ui'
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
    if (value !== null) {
      total += value
      count++
    }
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
    if (value !== null) {
      total += value
      count++
    }
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
    if (!best || value > best.value) {
      best = { id, value }
    }
  }
  return best
}

function StatItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="px-3 py-2 rounded-lg bg-surface3">
      <p className="text-xs text-muted mb-0.5">{label}</p>
      <p className="text-sm font-semibold text-white">{value}</p>
    </div>
  )
}

function ConsumerItem({
  label,
  nodeId,
  value,
}: {
  label: string
  nodeId: string | null
  value: string
}) {
  return (
    <div className="px-3 py-3 rounded-lg bg-surface3">
      <p className="text-xs text-muted mb-1">{label}</p>
      {nodeId ? (
        <>
          <p className="text-sm font-medium text-white">{shortNodeId(nodeId)}</p>
          <p className="text-xs text-accent mt-0.5">{value}</p>
        </>
      ) : (
        <p className="text-sm text-muted">—</p>
      )}
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

    const serverCount = allEntries.filter(([id]) =>
  /server-\d+$/i.test(id)
).length

    const alertCount = allEntries.filter(
      ([, n]) => n.state === 'warning' || n.state === 'critical',
    ).length

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

    const healthLabel =
      alertCount === 0 ? 'Healthy' : criticalCount > 0 ? 'Critical' : 'Warning'

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
      driftSubtitle: criticalCount > 0 ? `${criticalCount} critical` : 'No critical',
      driftColor: criticalCount > 0 ? ('red' as const) : ('green' as const),
      cpuSubtitle: healthLabel,
      cpuColor:
        alertCount === 0
          ? ('green' as const)
          : criticalCount > 0
            ? ('red' as const)
            : ('yellow' as const),
      powerSubtitle: 'Live aggregate',
      overview: {
        totalNodes: String(allEntries.length),
        totalEdges: String(Object.keys(edges).length),
        healthyNodes: String(healthyCount),
        nodesWithMetrics: String(metricEntries.length),
        chaos: chaos_active ? 'Active' : 'Inactive',
        tickCount: String(tick_count),
      },
      resources: {
        cpu: cpuAvg !== null ? `${formatNumber(cpuAvg, 1)}%` : '—',
        memory: memAvg !== null ? `${formatNumber(memAvg, 1)}%` : '—',
        temperature: tempAvg !== null ? `${formatNumber(tempAvg, 1)}°C` : '—',
        power: totalPowerW !== null ? `${formatNumber(totalPowerW, 0)} W` : '—',
        iops: totalIops !== null ? formatNumber(totalIops, 0) : '—',
      },
      consumers: {
        cpu: topCpu
          ? { id: topCpu.id, value: `${formatNumber(topCpu.value, 1)}%` }
          : null,
        memory: topMem
          ? { id: topMem.id, value: `${formatNumber(topMem.value, 1)}%` }
          : null,
        power: topPower
          ? { id: topPower.id, value: `${formatNumber(topPower.value, 0)} W` }
          : null,
        temperature: topTemp
          ? { id: topTemp.id, value: `${formatNumber(topTemp.value, 1)}°C` }
          : null,
      },
      tableRows,
    }
  }, [telemetry.data])

  return (
    <div>
      <PageHeader
        title="Infrastructure Overview"
        subtitle="Real-time infrastructure health and capacity metrics"
      />

      {telemetry.error && (
        <ErrorBanner message={`Backend unavailable: ${telemetry.error}`} />
      )}

      {telemetry.loading && !data ? (
        <LoadingSpinner label="Fetching live metrics..." />
      ) : data ? (
        <div className="space-y-6">
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
            <MetricCard
              label="Active Servers"
              value={data.servers}
              subtitle="Compute nodes in telemetry"
              subtitleColor="green"
              icon={Server}
              iconColor="#4d9fff"
            />
            <MetricCard
              label="Power Usage"
              value={data.power}
              subtitle={data.powerSubtitle}
              subtitleColor="green"
              icon={Zap}
              iconColor="#00d4aa"
            />
            <MetricCard
              label="Drift Alerts"
              value={data.drift}
              subtitle={data.driftSubtitle}
              subtitleColor={data.driftColor}
              icon={ShieldAlert}
              iconColor="#f87171"
            />
            <MetricCard
              label="CPU Utilization"
              value={data.cpu}
              subtitle={data.cpuSubtitle}
              subtitleColor={data.cpuColor}
              icon={Cpu}
              iconColor="#a78bfa"
            />
          </div>

          <Card title="Infrastructure Health Overview">
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
              <StatItem label="Total Nodes" value={data.overview.totalNodes} />
              <StatItem label="Total Connections" value={data.overview.totalEdges} />
              <StatItem label="Healthy Nodes" value={data.overview.healthyNodes} />
              <StatItem label="Nodes with Metrics" value={data.overview.nodesWithMetrics} />
              <StatItem label="Chaos Status" value={data.overview.chaos} />
              <StatItem label="Tick Count" value={data.overview.tickCount} />
            </div>
          </Card>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Card title="Resource Summary">
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                <StatItem label="Average CPU" value={data.resources.cpu} />
                <StatItem label="Average Memory" value={data.resources.memory} />
                <StatItem label="Average Temperature" value={data.resources.temperature} />
                <StatItem label="Total Power" value={data.resources.power} />
                <StatItem label="Total Disk IOPS" value={data.resources.iops} />
              </div>
            </Card>

            <Card title="Top Resource Consumers">
              <div className="grid grid-cols-2 gap-3">
                <ConsumerItem
                  label="Highest CPU"
                  nodeId={data.consumers.cpu?.id ?? null}
                  value={data.consumers.cpu?.value ?? '—'}
                />
                <ConsumerItem
                  label="Highest Memory"
                  nodeId={data.consumers.memory?.id ?? null}
                  value={data.consumers.memory?.value ?? '—'}
                />
                <ConsumerItem
                  label="Highest Power"
                  nodeId={data.consumers.power?.id ?? null}
                  value={data.consumers.power?.value ?? '—'}
                />
                <ConsumerItem
                  label="Highest Temperature"
                  nodeId={data.consumers.temperature?.id ?? null}
                  value={data.consumers.temperature?.value ?? '—'}
                />
              </div>
            </Card>
          </div>

          <Card
            title="Node Metrics"
            subtitle={`${data.tableRows.length} nodes reporting metric data`}
          >
            {data.tableRows.length === 0 ? (
              <p className="text-sm text-muted">No nodes with metric data available.</p>
            ) : (
              <div className="overflow-x-auto -mx-5">
                <table className="w-full">
                  <thead>
                    <tr>
                      <th className="table-head">Node Name</th>
                      <th className="table-head">Role</th>
                      <th className="table-head">State</th>
                      <th className="table-head">CPU %</th>
                      <th className="table-head">Memory %</th>
                      <th className="table-head">Power Watts</th>
                      <th className="table-head">Temperature</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.tableRows.map((row) => (
                      <tr key={row.id} className="hover:bg-surface3/40 transition">
                        <td className="table-cell font-medium text-white">{row.name}</td>
                        <td className="table-cell text-gray-400 capitalize">
                          {row.role.replace(/-/g, ' ')}
                        </td>
                        <td className="table-cell">
                          <span className={`badge capitalize ${stateBadgeClass(row.state)}`}>
                            {row.state}
                          </span>
                        </td>
                        <td className="table-cell text-gray-400">
                          {row.cpu !== null ? `${formatNumber(row.cpu, 1)}%` : '—'}
                        </td>
                        <td className="table-cell text-gray-400">
                          {row.memory !== null ? `${formatNumber(row.memory, 1)}%` : '—'}
                        </td>
                        <td className="table-cell text-gray-400">
                          {row.power !== null ? formatNumber(row.power, 0) : '—'}
                        </td>
                        <td className="table-cell text-gray-400">
                          {row.temp !== null ? `${formatNumber(row.temp, 1)}°C` : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      ) : null}
    </div>
  )
}
