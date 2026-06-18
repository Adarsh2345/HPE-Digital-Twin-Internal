import { PageHeader, Card, LoadingSpinner, ErrorBanner, EmptyState } from '../components/ui'
import { usePolling } from '../hooks/usePolling'
import { api } from '../api/client'

type AnomalyStatus = {
  trained: boolean
  if_devices: string[]
  rf_devices: string[]
  model_path: string
}

function getAnomalyStatus() {
  return api<AnomalyStatus>('GET', '/api/v1/analytics/anomaly/status')
}

export default function AnomalyPage() {
  const { data, loading, error } = usePolling(getAnomalyStatus, 8000)

  return (
    <div>
      <PageHeader
        title="Anomaly Detection"
        subtitle="Isolation Forest and Random Forest detector status"
      />

      {error && <ErrorBanner message={String(error)} />}

      {data && (
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-4 mb-4">
          <Card title="Detector Status">
            <div className="flex items-center gap-2">
              <span
                className={`badge capitalize ${
                  data.trained
                    ? 'bg-green-500/20 text-green-300'
                    : 'bg-red-500/20 text-red-300'
                }`}
              >
                {data.trained ? 'Trained' : 'Not Trained'}
              </span>
            </div>
          </Card>

          <Card title="IF Models">
            <p className="text-2xl font-bold text-white">
              {data.if_devices.length}
            </p>
            <p className="text-xs text-muted">
              Isolation Forest models
            </p>
          </Card>

          <Card title="RF Models">
            <p className="text-2xl font-bold text-white">
              {data.rf_devices.length}
            </p>
            <p className="text-xs text-muted">
              Random Forest models
            </p>
          </Card>

          <Card title="Model Path">
            <p className="text-xs font-mono text-gray-400 break-all">
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
          <div className="overflow-x-auto -mx-5">
            <table className="w-full">
              <thead>
                <tr>
                  <th className="table-head">Device</th>
                  <th className="table-head">Isolation Forest</th>
                  <th className="table-head">Random Forest</th>
                  <th className="table-head">Status</th>
                </tr>
              </thead>

              <tbody>
                {Array.from(
                  new Set([...data.if_devices, ...data.rf_devices]),
                ).map((device, i) => (
                  <tr
                    key={i}
                    className="hover:bg-surface3/40 transition"
                  >
                    <td className="table-cell font-medium text-white">
                      {device}
                    </td>

                    <td className="table-cell text-gray-400">
                      {data.if_devices.includes(device) ? 'Available' : '—'}
                    </td>

                    <td className="table-cell text-gray-400">
                      {data.rf_devices.includes(device) ? 'Available' : '—'}
                    </td>

                    <td className="table-cell">
                      <span
                        className={`badge ${
                          data.trained
                            ? 'bg-green-500/20 text-green-300'
                            : 'bg-red-500/20 text-red-300'
                        }`}
                      >
                        {data.trained ? 'Ready' : 'Unavailable'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}