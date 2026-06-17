import { useMemo } from 'react'
import { Server, Zap, ShieldAlert, Cpu } from 'lucide-react'
import MetricCard from '../components/MetricCard'
import { PageHeader, LoadingSpinner, ErrorBanner } from '../components/ui'
import { usePolling } from '../hooks/usePolling'
import { getTelemetry } from '../api/telemetry'
import { getHealth } from '../api/reports'
import { getNodes } from '../api/topology'
import { aggregatePowerKw, averageCpu, formatNumber } from '../utils/format'

export default function Dashboard() {
  const telemetry = usePolling(getTelemetry, 4000)
  const health = usePolling(getHealth, 4000)
  const nodes = usePolling(getNodes, 10000)

  const metrics = useMemo(() => {
    const powerKw = telemetry.data ? aggregatePowerKw(telemetry.data.nodes) : null
    const cpuAvg = telemetry.data ? averageCpu(telemetry.data.nodes) : null
    const serverCount =
      nodes.data?.filter((n) => n.role === 'compute-node').length ?? null
    const driftCount =
      health.data
        ? health.data.critical_nodes.length + health.data.warning_nodes.length
        : null
    const criticalCount = health.data?.critical_nodes.length ?? 0

    const healthLabel =
      health.data?.overall_health === 'healthy'
        ? 'Healthy'
        : health.data?.overall_health === 'warning'
          ? 'Warning'
          : health.data?.overall_health === 'critical'
            ? 'Critical'
            : '—'

    return {
      servers: serverCount !== null ? String(serverCount) : '—',
      power: powerKw !== null ? `${formatNumber(powerKw, 0)} kW` : '—',
      drift: driftCount !== null ? String(driftCount) : '—',
      cpu: cpuAvg !== null ? `${formatNumber(cpuAvg, 0)}%` : '—',
      driftSubtitle: criticalCount > 0 ? `${criticalCount} critical` : 'No critical',
      driftColor: criticalCount > 0 ? ('red' as const) : ('green' as const),
      cpuSubtitle: healthLabel,
      cpuColor:
        health.data?.overall_health === 'healthy'
          ? ('green' as const)
          : health.data?.overall_health === 'critical'
            ? ('red' as const)
            : ('yellow' as const),
      powerSubtitle: telemetry.data ? 'Live aggregate' : '—',
    }
  }, [telemetry.data, health.data, nodes.data])

  const loading = telemetry.loading && health.loading
  const error = telemetry.error ?? health.error

  return (
    <div>
      <PageHeader
        title="Infrastructure Overview"
        subtitle="Real-time infrastructure health and capacity metrics"
      />

      {error && <ErrorBanner message={`Backend unavailable: ${error}`} />}

      {loading ? (
        <LoadingSpinner label="Fetching live metrics..." />
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
          <MetricCard
            label="Active Servers"
            value={metrics.servers}
            subtitle="From topology"
            subtitleColor="green"
            icon={Server}
            iconColor="#4d9fff"
          />
          <MetricCard
            label="Power Usage"
            value={metrics.power}
            subtitle={metrics.powerSubtitle}
            subtitleColor="green"
            icon={Zap}
            iconColor="#00d4aa"
          />
          <MetricCard
            label="Drift Alerts"
            value={metrics.drift}
            subtitle={metrics.driftSubtitle}
            subtitleColor={metrics.driftColor}
            icon={ShieldAlert}
            iconColor="#f87171"
          />
          <MetricCard
            label="CPU Utilization"
            value={metrics.cpu}
            subtitle={metrics.cpuSubtitle}
            subtitleColor={metrics.cpuColor}
            icon={Cpu}
            iconColor="#a78bfa"
          />
        </div>
      )}
    </div>
  )
}
