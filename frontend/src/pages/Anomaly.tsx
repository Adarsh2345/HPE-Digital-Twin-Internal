import { useState } from 'react'
import {
  PageHeader,
  Card,
  LoadingSpinner,
  ErrorBanner,
  EmptyState,
} from '../components/ui'
import { usePolling } from '../hooks/usePolling'
import { api } from '../api/client'

type AnomalyStatus = {
  trained: boolean
  if_devices: string[]
  rf_devices: string[]
  model_path: string
}

function getAnomalyStatus() {
  return api<AnomalyStatus>(
    'GET',
    '/api/v1/analytics/anomaly/status',
  )
}

export default function AnomalyPage() {
  const { data, loading, error } = usePolling(
    getAnomalyStatus,
    8000,
  )

  const [nodeId, setNodeId] = useState(
    'droplet-1-tor1/server-1',
  )
  const [scanning, setScanning] = useState(false)
  const [scanError, setScanError] = useState<string | null>(null)
  const [scanResult, setScanResult] = useState<any>(null)

  async function runScan() {
    try {
      setScanning(true)
      setScanError(null)

      const result = await api(
        'POST',
        `/api/v1/analytics/anomaly/detect/${encodeURIComponent(
          nodeId,
        )}`,
        {
          metrics: {
            cpu_percent: 92,
            memory_percent: 88,
            disk_iops: 3900,
            power_watts: 310,
            temperature_celsius: 78,
          },
        },
      )

      setScanResult(result)
    } catch (err: any) {
      setScanError(err.message ?? 'Scan failed')
    } finally {
      setScanning(false)
    }
  }

  return (
    <div>
      <PageHeader
        title="Anomaly Detection"
        subtitle="Isolation Forest and Random Forest detector status"
      />

      {(error || scanError) && (
        <ErrorBanner
          message={String(error ?? scanError)}
        />
      )}

      {data && (
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-4 mb-4">
          <Card title="Detector Status">
            <div className="flex items-center gap-2">
              <span
                className={`badge ${
                  data.trained
                    ? 'bg-green-500/20 text-green-300'
                    : 'bg-red-500/20 text-red-300'
                }`}
              >
                {data.trained
                  ? 'Trained'
                  : 'Not Trained'}
              </span>
            </div>
          </Card>

          <Card title="IF Models">
            <p className="text-2xl font-bold text-white">
              {data.if_devices.length}
            </p>
            <p className="text-xs text-muted">
              Isolation Forest Models
            </p>
          </Card>

          <Card title="RF Models">
            <p className="text-2xl font-bold text-white">
              {data.rf_devices.length}
            </p>
            <p className="text-xs text-muted">
              Random Forest Models
            </p>
          </Card>

          <Card title="Model Path">
            <p className="text-xs font-mono break-all text-gray-400">
              {data.model_path}
            </p>
          </Card>
        </div>
      )}

      <Card
        title="Anomaly Detection Models"
        subtitle="Registered detector models per device"
      >
        {loading ? (
          <LoadingSpinner />
        ) : !data ? (
          <EmptyState
            title="No anomaly detector data"
            description="Detector status endpoint returned no data."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr>
                  <th className="table-head">
                    Device
                  </th>
                  <th className="table-head">
                    Isolation Forest
                  </th>
                  <th className="table-head">
                    Random Forest
                  </th>
                  <th className="table-head">
                    Status
                  </th>
                </tr>
              </thead>

              <tbody>
                {Array.from(
                  new Set([
                    ...data.if_devices,
                    ...data.rf_devices,
                  ]),
                ).map((device) => (
                  <tr key={device}>
                    <td className="table-cell">
                      {device}
                    </td>

                    <td className="table-cell">
                      {data.if_devices.includes(
                        device,
                      )
                        ? 'Available'
                        : '-'}
                    </td>

                    <td className="table-cell">
                      {data.rf_devices.includes(
                        device,
                      )
                        ? 'Available'
                        : '-'}
                    </td>

                    <td className="table-cell">
                      <span
                        className={`badge ${
                          data.trained
                            ? 'bg-green-500/20 text-green-300'
                            : 'bg-red-500/20 text-red-300'
                        }`}
                      >
                        {data.trained
                          ? 'Ready'
                          : 'Unavailable'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <div className="mt-6">
        <Card
          title="Run Anomaly Detection"
          subtitle="POST /api/v1/analytics/anomaly/detect/{node_id}"
        >
          <div className="flex gap-4 mb-4">
            <input
              value={nodeId}
              onChange={(e) =>
                setNodeId(e.target.value)
              }
              className="input flex-1"
              placeholder="Node ID"
            />

            <button
              onClick={runScan}
              disabled={scanning}
              className="btn btn-primary"
            >
              {scanning
                ? 'Scanning...'
                : 'Run Scan'}
            </button>
          </div>

          {scanning ? (
            <LoadingSpinner />
          ) : !scanResult ? (
            <EmptyState
              title="No Scan Results"
              description="Run anomaly detection to view results."
            />
          ) : (
            <div className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <Card title="Alert Level">
                  <p className="text-xl font-bold text-red-400">
                    {scanResult.alert_level}
                  </p>
                </Card>

                <Card title="Node">
                  <p className="font-mono text-sm break-all">
                    {scanResult.node_id}
                  </p>
                </Card>

                <Card title="Anomaly Type">
                  <p>
                    {
                      scanResult.anomaly
                        ?.anomaly_type
                    }
                  </p>
                </Card>

                <Card title="RF Confidence">
                  <p>
                    {Math.round(
                      (scanResult.anomaly
                        ?.rf_confidence ??
                        0) * 100,
                    )}
                    %
                  </p>
                </Card>
              </div>

              <Card title="Triggers">
                <ul className="space-y-2">
                  {scanResult.triggers?.map(
                    (
                      trigger: string,
                      index: number,
                    ) => (
                      <li key={index}>
                        • {trigger}
                      </li>
                    ),
                  )}
                </ul>
              </Card>

              <Card title="Recommendations">
                <ul className="space-y-2">
                  {scanResult.recommendations?.map(
                    (
                      recommendation: string,
                      index: number,
                    ) => (
                      <li
                        key={index}
                        className="text-green-400"
                      >
                        ✓ {recommendation}
                      </li>
                    ),
                  )}
                </ul>
              </Card>

              <Card title="Raw API Response">
                <pre className="text-xs overflow-auto whitespace-pre-wrap">
                  {JSON.stringify(
                    scanResult,
                    null,
                    2,
                  )}
                </pre>
              </Card>
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}