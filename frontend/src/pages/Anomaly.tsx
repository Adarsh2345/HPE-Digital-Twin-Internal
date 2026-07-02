import { useState, useMemo, useRef, useEffect } from 'react'
import {
  Search,
  SlidersHorizontal,
  Download,
  RefreshCw,
  Play,
  Square,
  Activity,
  CheckCircle,
  AlertTriangle,
  AlertOctagon,
  Shield,
  Database,
  Sparkles,
  Cpu,
  Layers,
  Zap,
  Thermometer,
  Eye,
  Settings,
  Info
} from 'lucide-react'
import {
  PageHeader,
  Card,
  LoadingSpinner,
  ErrorBanner,
  EmptyState,
} from '../components/ui'
import { usePolling } from '../hooks/usePolling'
import { api } from '../api/client'
import { getAnomalyStatus, type AnomalyDetectResult } from '../api/analytics'
import { getTelemetry } from '../api/telemetry'

const shortNodeId = (id: string) => (id.includes('/') ? id.split('/').pop() || id : id)

export default function AnomalyPage() {
  // Model and training status
  const {
    data: statusData,
    loading: statusLoading,
    error: statusError,
    refresh: refreshStatus,
  } = usePolling(getAnomalyStatus, 8000)

  // Search, filter, and sort state
  const [searchQuery, setSearchQuery] = useState('')
  const [severityFilter, setSeverityFilter] = useState<'all' | 'critical' | 'warning' | 'healthy'>('all')
  const [sortBy, setSortBy] = useState<'name' | 'severity' | 'confidence'>('name')
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)

  // Model training state
  const [training, setTraining] = useState(false)
  const [trainDays, setTrainDays] = useState('7')
  const [trainChaosSnaps, setTrainChaosSnaps] = useState('3000')
  const [trainingError, setTrainingError] = useState<string | null>(null)

  // Single metrics scan state
  const [singleNodeId, setSingleNodeId] = useState('droplet-1-tor1/server-1')
  const [mCpu, setMCpu] = useState('92')
  const [mMem, setMMem] = useState('88')
  const [mIops, setMIops] = useState('3900')
  const [mPwr, setMPwr] = useState('310')
  const [mTemp, setMTemp] = useState('78')
  const [scanningSingle, setScanningSingle] = useState(false)
  const [singleScanError, setSingleScanError] = useState<string | null>(null)

  // Harvester / Scan All state
  const [scanAllStatus, setScanAllStatus] = useState<'idle' | 'scanning' | 'completed' | 'failed' | 'cancelled'>('idle')
  const [scannedCount, setScannedCount] = useState(0)
  const [totalCount, setTotalCount] = useState(0)
  const [scanErrors, setScanErrors] = useState(0)
  const [scanResults, setScanResults] = useState<Record<string, AnomalyDetectResult>>({})
  const [scanDuration, setScanDuration] = useState(0)
  const [lastScanTimestamp, setLastScanTimestamp] = useState<string | null>(null)
  const [generalError, setGeneralError] = useState<string | null>(null)

  const cancelScanRef = useRef(false)

  // Orchestrate client-side sequential scanning to prevent backend overloading
  const handleScanAll = async () => {
    try {
      setScanAllStatus('scanning')
      setScannedCount(0)
      setScanErrors(0)
      setScanResults({})
      setGeneralError(null)
      cancelScanRef.current = false

      const startTime = Date.now()
      setScanDuration(0)

      // Fetch active topology list from telemetry API
      const telemetry = await getTelemetry()
      if (!telemetry || !telemetry.nodes) {
        throw new Error('Telemetry database returned empty node list')
      }

      const nodes = Object.entries(telemetry.nodes)
      const total = nodes.length
      setTotalCount(total)

      const timerId = setInterval(() => {
        setScanDuration(Math.round((Date.now() - startTime) / 1000))
      }, 1000)

      const tempResults: Record<string, AnomalyDetectResult> = {}

      for (let i = 0; i < total; i++) {
        if (cancelScanRef.current) {
          setScanAllStatus('cancelled')
          clearInterval(timerId)
          return
        }

        const [nodeId, nodeData] = nodes[i]
        try {
          const res = await api<AnomalyDetectResult>(
            'POST',
            `/api/v1/analytics/anomaly/detect/${encodeURIComponent(nodeId)}`,
            { metrics: nodeData.metrics || {} }
          )
          tempResults[nodeId] = res
        } catch (err) {
          console.error(`Failed scan on node ${nodeId}:`, err)
          setScanErrors((prev) => prev + 1)
          // Insert failed run details locally to maintain dashboard integrity
          tempResults[nodeId] = {
            node_id: nodeId,
            alert_level: 'unknown',
            triggers: ['Connection error during node scan'],
            recommendations: ['Check FastAPI background server log', 'Ensure ML models are trained'],
            anomaly: { anomaly: false, error: true }
          } as any
        }

        setScanResults({ ...tempResults })
        setScannedCount(i + 1)
      }

      clearInterval(timerId)
      setScanAllStatus('completed')
      setLastScanTimestamp(new Date().toLocaleTimeString())
    } catch (err: any) {
      setScanAllStatus('failed')
      setGeneralError(err.message || 'Harvester loop failed')
    }
  }

  const handleCancelScan = () => {
    cancelScanRef.current = true
  }

  // Model training execution
  const handleTrainModels = async () => {
    try {
      setTraining(true)
      setTrainingError(null)
      await api(
        'POST',
        `/api/v1/analytics/anomaly/train?days=${trainDays}&chaos_snapshots=${trainChaosSnaps}`
      )
      await refreshStatus()
    } catch (err: any) {
      setTrainingError(err.message || 'Model training failed')
    } finally {
      setTraining(false)
    }
  }

  // Single test metrics scan execution
  const handleSingleScan = async () => {
    try {
      setScanningSingle(true)
      setSingleScanError(null)
      const res = await api<AnomalyDetectResult>(
        'POST',
        `/api/v1/analytics/anomaly/detect/${encodeURIComponent(singleNodeId)}`,
        {
          metrics: {
            cpu_percent: parseFloat(mCpu) || 0,
            memory_percent: parseFloat(mMem) || 0,
            disk_iops: parseFloat(mIops) || 0,
            power_watts: parseFloat(mPwr) || 0,
            temperature_celsius: parseFloat(mTemp) || 0,
          },
        }
      )
      setScanResults((prev) => ({
        ...prev,
        [singleNodeId]: res,
      }))
      setSelectedNodeId(singleNodeId)
    } catch (err: any) {
      setSingleScanError(err.message || 'Failed single prediction')
    } finally {
      setScanningSingle(false)
    }
  }

  // Export JSON Report Utility
  const handleExportJSON = () => {
    const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(scanResults, null, 2))
    const downloadAnchor = document.createElement('a')
    downloadAnchor.setAttribute('href', dataStr)
    downloadAnchor.setAttribute('download', `anomaly_scan_${new Date().toISOString().split('T')[0]}.json`)
    document.body.appendChild(downloadAnchor)
    downloadAnchor.click()
    downloadAnchor.remove()
  }

  // Aggregate results and statistics
  const stats = useMemo(() => {
    const results = Object.values(scanResults)
    const total = results.length
    if (total === 0) return { critical: 0, warning: 0, healthy: 0, anomalies: 0, successRate: 0, avgConfidence: 0 }

    let critical = 0
    let warning = 0
    let healthy = 0
    let successfulScans = 0
    let confidenceSum = 0
    let confidenceCount = 0

    results.forEach((r) => {
      if (r.anomaly?.error) return
      successfulScans++
      
      const level = r.alert_level || 'normal'
      if (level === 'critical') critical++
      else if (level === 'warning') warning++
      else if (level === 'normal') healthy++

      const rfConf = (r.anomaly as any)?.rf_confidence ?? (r.anomaly as any)?.score
      if (typeof rfConf === 'number') {
        confidenceSum += rfConf
        confidenceCount++
      }
    })

    return {
      critical,
      warning,
      healthy,
      anomalies: critical + warning,
      successRate: Math.round((successfulScans / total) * 100),
      avgConfidence: confidenceCount > 0 ? Math.round((confidenceSum / confidenceCount) * 100) : 0,
    }
  }, [scanResults])

  // Filter & Sort node list
  const filteredNodes = useMemo(() => {
    const results = Object.entries(scanResults)
    
    return results
      .filter(([id, data]) => {
        // Text Search
        const nameMatch = id.toLowerCase().includes(searchQuery.toLowerCase())
        if (!nameMatch) return false

        // Severity Filter
        const level = data.alert_level || 'normal'
        if (severityFilter === 'all') return true
        if (severityFilter === 'critical') return level === 'critical'
        if (severityFilter === 'warning') return level === 'warning'
        if (severityFilter === 'healthy') return level === 'normal'
        return true
      })
      .sort((a, b) => {
        const idA = a[0]
        const idB = b[0]
        const dataA = a[1]
        const dataB = b[1]

        if (sortBy === 'name') {
          return idA.localeCompare(idB)
        } else if (sortBy === 'severity') {
          const order: Record<string, number> = { critical: 0, warning: 1, normal: 2, unknown: 3 }
          return (order[dataA.alert_level] ?? 3) - (order[dataB.alert_level] ?? 3)
        } else if (sortBy === 'confidence') {
          const confA = (dataA.anomaly as any)?.rf_confidence ?? 0
          const confB = (dataB.anomaly as any)?.rf_confidence ?? 0
          return confB - confA
        }
        return 0
      })
  }, [scanResults, searchQuery, severityFilter, sortBy])

  // Get active inspector data
  const inspectorNode = selectedNodeId ? scanResults[selectedNodeId] : null

  // Auto-select worst node upon completed scan
  useEffect(() => {
    if (scanAllStatus === 'completed') {
      const entries = Object.entries(scanResults)
      if (entries.length > 0) {
        const criticalNode = entries.find(([, data]) => data.alert_level === 'critical')
        const warningNode = entries.find(([, data]) => data.alert_level === 'warning')
        const firstNode = entries[0]
        const target = criticalNode || warningNode || firstNode
        setSelectedNodeId(target[0])
      }
    }
  }, [scanAllStatus])

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <PageHeader
          title="Anomaly Detection Room"
          subtitle="Enterprise analytics combining rule thresholds with Isolation Forest & RandomForest models"
        />

        <div className="flex flex-wrap items-center gap-2">
          {scanAllStatus === 'scanning' ? (
            <button
              onClick={handleCancelScan}
              className="px-4 py-2 text-sm font-semibold rounded-lg bg-red-500/25 border border-red-500/30 text-red-300 hover:bg-red-500/35 transition flex items-center gap-2"
            >
              <Square className="w-3.5 h-3.5 fill-current" />
              Cancel Scan
            </button>
          ) : (
            <button
              onClick={handleScanAll}
              disabled={statusData?.trained === false}
              className="btn-primary flex items-center gap-2 shadow-lg shadow-accent/20"
            >
              <Play className="w-3.5 h-3.5 fill-current" />
              Scan All Nodes
            </button>
          )}

          <button
            onClick={handleExportJSON}
            disabled={Object.keys(scanResults).length === 0}
            className="px-4 py-2 text-sm font-semibold rounded-lg bg-surface3 border border-border text-gray-200 hover:border-gray-500 disabled:opacity-50 transition flex items-center gap-2"
          >
            <Download className="w-3.5 h-3.5" />
            Export JSON
          </button>

          <button
            onClick={refreshStatus}
            className="p-2 rounded-lg bg-surface3 border border-border text-muted hover:text-white transition"
            title="Refresh Detector Status"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {(statusError || trainingError || generalError) && (
        <ErrorBanner message={String(statusError || trainingError || generalError)} />
      )}

      {/* MODEL STATE STATUS BAR */}
      {statusData && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Card className="flex items-center gap-4 relative overflow-hidden">
            <div className="p-3 rounded-lg bg-surface3 border border-border/80 text-accent">
              <Shield className="w-5 h-5" />
            </div>
            <div>
              <p className="text-xs text-muted">Model Status</p>
              <div className="flex items-center gap-2 mt-0.5">
                <span className={`w-2 h-2 rounded-full ${statusData.trained ? 'bg-accent animate-pulse shadow-glow' : 'bg-red-400'}`} />
                <span className="text-sm font-semibold text-white">
                  {statusData.trained ? 'Active & Calibrated' : 'Needs Training'}
                </span>
              </div>
            </div>
          </Card>

          <Card className="flex items-center gap-4">
            <div className="p-3 rounded-lg bg-surface3 border border-border/80 text-blue-400">
              <Database className="w-5 h-5" />
            </div>
            <div>
              <p className="text-xs text-muted">Isolation Forests</p>
              <p className="text-lg font-bold text-white mt-0.5">{statusData.if_devices.length} Devices</p>
            </div>
          </Card>

          <Card className="flex items-center gap-4">
            <div className="p-3 rounded-lg bg-surface3 border border-border/80 text-purple-400">
              <Layers className="w-5 h-5" />
            </div>
            <div>
              <p className="text-xs text-muted">Random Forests</p>
              <p className="text-lg font-bold text-white mt-0.5">{statusData.rf_devices.length} Classifiers</p>
            </div>
          </Card>

          <Card className="flex items-center gap-4">
            <div className="p-3 rounded-lg bg-surface3 border border-border/80 text-muted">
              <Settings className="w-5 h-5" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-xs text-muted">Model Registry Location</p>
              <p className="text-xs font-mono truncate text-gray-400 mt-0.5" title={statusData.model_path}>
                {statusData.model_path || 'models/anomaly_detector.pkl'}
              </p>
            </div>
          </Card>
        </div>
      )}

      {/* SCANNING PROGRESS OVERLAY */}
      {scanAllStatus === 'scanning' && (
        <Card className="relative border-accent/40 bg-accent-dim/5 overflow-hidden">
          <div className="absolute top-0 left-0 h-1 bg-gradient-to-r from-accent to-blue-500 animate-pulse w-full" />
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="flex-1 space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="font-semibold text-white flex items-center gap-2">
                  <Activity className="w-4 h-4 text-accent animate-spin" />
                  Scanning Infrastructure Telemetry...
                </span>
                <span className="font-mono text-accent">
                  {scannedCount} / {totalCount} Nodes ({Math.round((scannedCount / totalCount) * 100)}%)
                </span>
              </div>
              <div className="h-2 w-full bg-surface3 rounded-full overflow-hidden border border-border">
                <div
                  className="h-full bg-accent rounded-full transition-all duration-300"
                  style={{ width: `${(scannedCount / totalCount) * 100}%` }}
                />
              </div>
            </div>
            <div className="flex gap-4 border-l border-border pl-4 pr-2 font-mono text-xs text-muted">
              <div>
                <p>Elapsed Time</p>
                <p className="text-white font-semibold text-sm">{scanDuration}s</p>
              </div>
              <div>
                <p>Failed Links</p>
                <p className="text-red-400 font-semibold text-sm">{scanErrors}</p>
              </div>
            </div>
          </div>
        </Card>
      )}

      {/* STATISTICS OVERVIEW CARD (IF RESULTS AVAILABLE) */}
      {Object.keys(scanResults).length > 0 && (
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
          <div className="card p-4 flex flex-col justify-between border-red-500/20 bg-red-500/5">
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted font-medium">Critical Breaches</span>
              <AlertOctagon className="w-4 h-4 text-red-400" />
            </div>
            <div className="mt-4">
              <p className="text-3xl font-extrabold text-red-400">{stats.critical}</p>
              <p className="text-[10px] text-muted mt-1">Requires immediate failover</p>
            </div>
          </div>

          <div className="card p-4 flex flex-col justify-between border-yellow-500/20 bg-yellow-500/5">
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted font-medium">Warning Anomalies</span>
              <AlertTriangle className="w-4 h-4 text-yellow-400" />
            </div>
            <div className="mt-4">
              <p className="text-3xl font-extrabold text-yellow-400">{stats.warning}</p>
              <p className="text-[10px] text-muted mt-1">Metric boundary outliers</p>
            </div>
          </div>

          <div className="card p-4 flex flex-col justify-between border-green-500/20 bg-green-500/5">
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted font-medium">Healthy Devices</span>
              <CheckCircle className="w-4 h-4 text-green-400" />
            </div>
            <div className="mt-4">
              <p className="text-3xl font-extrabold text-green-400">{stats.healthy}</p>
              <p className="text-[10px] text-muted mt-1">Within statistical bounds</p>
            </div>
          </div>

          <div className="card p-4 flex flex-col justify-between">
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted font-medium">Avg Classifier Confidence</span>
              <Sparkles className="w-4 h-4 text-accent" />
            </div>
            <div className="mt-4">
              <p className="text-3xl font-extrabold text-white">{stats.avgConfidence}%</p>
              <p className="text-[10px] text-muted mt-1">Random Forest probability</p>
            </div>
          </div>

          <div className="card p-4 flex flex-col justify-between col-span-2 lg:col-span-1">
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted font-medium">Harvester Success Rate</span>
              <Activity className="w-4 h-4 text-blue-400" />
            </div>
            <div className="mt-4">
              <p className="text-3xl font-extrabold text-white">{stats.successRate}%</p>
              <p className="text-[10px] text-muted mt-1">
                Completed in {scanDuration}s {lastScanTimestamp && `at ${lastScanTimestamp}`}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* HEATMAP GRID VISUALIZATION */}
      {Object.keys(scanResults).length > 0 && (
        <Card title="Infrastructure Anomaly Heatmap" subtitle="Direct grid of all surveyed nodes. Click any cell to view model parameters.">
          <div className="grid grid-cols-4 sm:grid-cols-6 md:grid-cols-8 lg:grid-cols-12 gap-3">
            {Object.entries(scanResults).map(([id, res]) => {
              const level = res.alert_level || 'normal'
              const short = shortNodeId(id)
              
              let cellClass = ''
              let icon = null

              if (res.anomaly?.error) {
                cellClass = 'bg-surface3 border-border/50 text-muted'
                icon = <Info className="w-4 h-4" />
              } else if (level === 'critical') {
                cellClass = 'bg-red-500/10 border-red-500/30 text-red-400 hover:bg-red-500/20 hover:border-red-500/50 shadow-sm shadow-red-500/10'
                icon = <AlertOctagon className="w-4 h-4" />
              } else if (level === 'warning') {
                cellClass = 'bg-yellow-500/10 border-yellow-500/30 text-yellow-400 hover:bg-yellow-500/20 hover:border-yellow-500/50 shadow-sm shadow-yellow-500/10'
                icon = <AlertTriangle className="w-4 h-4" />
              } else {
                cellClass = 'bg-green-500/10 border-green-500/30 text-green-400 hover:bg-green-500/20 hover:border-green-500/50'
                icon = <CheckCircle className="w-4 h-4" />
              }

              const isSelected = selectedNodeId === id

              return (
                <div
                  key={id}
                  onClick={() => setSelectedNodeId(id)}
                  className={`p-3 rounded-lg border flex flex-col items-center justify-between text-center cursor-pointer transition-all duration-200 aspect-square group ${cellClass} ${
                    isSelected ? 'ring-2 ring-accent border-accent scale-105' : ''
                  }`}
                  title={`${id} (${level.toUpperCase()})`}
                >
                  <div className="text-[10px] font-mono font-medium truncate w-full text-gray-300 group-hover:text-white transition">
                    {short}
                  </div>
                  <div className="my-1.5">{icon}</div>
                  <div className="text-[8px] font-mono tracking-wider opacity-60 uppercase">
                    {level}
                  </div>
                </div>
              )
            })}
          </div>
        </Card>
      )}

      {/* DOUBLE COLUMN: LIST & DETAILS INSPECTOR */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <div className="xl:col-span-2 space-y-6">
          {/* SEARCH, FILTER, AND SORT TOOLBAR */}
          {Object.keys(scanResults).length > 0 ? (
            <Card className="p-4">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div className="relative flex-1">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted" />
                  <input
                    type="text"
                    placeholder="Search by Node ID..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full pl-10 pr-4 py-2 text-sm bg-surface3 border border-border rounded-lg text-gray-200 placeholder:text-muted focus:outline-none focus:border-accent/50"
                  />
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <div className="flex items-center gap-1.5 rounded-lg border border-border p-1 bg-surface3">
                    <button
                      onClick={() => setSeverityFilter('all')}
                      className={`px-3 py-1 rounded text-xs font-semibold transition ${
                        severityFilter === 'all' ? 'bg-accent text-bg' : 'text-muted hover:text-white'
                      }`}
                    >
                      All
                    </button>
                    <button
                      onClick={() => setSeverityFilter('critical')}
                      className={`px-3 py-1 rounded text-xs font-semibold transition ${
                        severityFilter === 'critical' ? 'bg-red-500/20 text-red-300' : 'text-muted hover:text-white'
                      }`}
                    >
                      Critical
                    </button>
                    <button
                      onClick={() => setSeverityFilter('warning')}
                      className={`px-3 py-1 rounded text-xs font-semibold transition ${
                        severityFilter === 'warning' ? 'bg-yellow-500/20 text-yellow-300' : 'text-muted hover:text-white'
                      }`}
                    >
                      Warning
                    </button>
                    <button
                      onClick={() => setSeverityFilter('healthy')}
                      className={`px-3 py-1 rounded text-xs font-semibold transition ${
                        severityFilter === 'healthy' ? 'bg-green-500/20 text-green-300' : 'text-muted hover:text-white'
                      }`}
                    >
                      Healthy
                    </button>
                  </div>

                  <div className="flex items-center gap-2 text-sm border border-border rounded-lg px-3 py-1.5 bg-surface3 text-gray-300">
                    <SlidersHorizontal className="w-3.5 h-3.5 text-muted" />
                    <span className="text-xs text-muted">Sort:</span>
                    <select
                      value={sortBy}
                      onChange={(e) => setSortBy(e.target.value as any)}
                      className="bg-transparent text-xs text-white focus:outline-none font-medium"
                    >
                      <option value="name">Node ID</option>
                      <option value="severity">Severity</option>
                      <option value="confidence">RF Confidence</option>
                    </select>
                  </div>
                </div>
              </div>
            </Card>
          ) : null}

          {/* TABLE SUMMARY LIST */}
          <Card
            title="Scan Summary"
            subtitle={`${filteredNodes.length} devices matching filters`}
          >
            {Object.keys(scanResults).length === 0 ? (
              <EmptyState
                title="No Scan Results Loaded"
                description="Run 'Scan All Nodes' to run anomaly detection across all active servers in parallel."
              />
            ) : filteredNodes.length === 0 ? (
              <EmptyState title="No matches found" description="Try broadening search terms or resetting severity filters." />
            ) : (
              <div className="overflow-x-auto -mx-5 -mb-5">
                <table className="w-full">
                  <thead>
                    <tr>
                      <th className="table-head">Device Name</th>
                      <th className="table-head">Alert Level</th>
                      <th className="table-head">IF Score</th>
                      <th className="table-head">RF Confidence</th>
                      <th className="table-head">Trigger Features</th>
                      <th className="table-head text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredNodes.map(([id, res]) => {
                      const level = res.alert_level || 'normal'
                      const ifScore = (res.anomaly as any)?.if_score ?? '—'
                      const rfConf = (res.anomaly as any)?.rf_confidence ?? (res.anomaly as any)?.score
                      const isSelected = selectedNodeId === id

                      let badgeCol = 'bg-green-500/10 text-green-300 border-green-500/20'
                      if (level === 'critical') badgeCol = 'bg-red-500/10 text-red-300 border-red-500/20'
                      else if (level === 'warning') badgeCol = 'bg-yellow-500/10 text-yellow-300 border-yellow-500/20'

                      return (
                        <tr
                          key={id}
                          onClick={() => setSelectedNodeId(id)}
                          className={`hover:bg-surface3/40 cursor-pointer transition ${
                            isSelected ? 'bg-surface3/60 border-l-2 border-accent' : ''
                          }`}
                        >
                          <td className="table-cell font-mono font-medium text-white text-xs">{id}</td>
                          <td className="table-cell">
                            <span className={`badge uppercase ${badgeCol}`}>{level}</span>
                          </td>
                          <td className="table-cell font-mono text-xs">{ifScore}</td>
                          <td className="table-cell font-mono text-xs">
                            {typeof rfConf === 'number' ? `${Math.round(rfConf * 100)}%` : '—'}
                          </td>
                          <td className="table-cell text-xs max-w-[180px] truncate text-gray-400">
                            {res.triggers && res.triggers.length > 0 ? (
                              <span className="flex flex-wrap gap-1">
                                {res.triggers.map((t) => (
                                  <span key={t} className="px-1.5 py-0.5 rounded bg-surface3 border border-border text-[10px]">
                                    {t.replace('if_anomaly:', '')}
                                  </span>
                                ))}
                              </span>
                            ) : (
                              '—'
                            )}
                          </td>
                          <td className="table-cell text-right text-xs">
                            <button
                              onClick={(e) => {
                                e.stopPropagation()
                                setSelectedNodeId(id)
                              }}
                              className="text-accent hover:underline flex items-center gap-1 ml-auto"
                            >
                              <Eye className="w-3.5 h-3.5" /> Inspect
                            </button>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          {/* HISTORICAL SPREAD & DISTRIBUTION CHART */}
          {Object.keys(scanResults).length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <Card title="Anomaly Severity Distribution" subtitle="Active node count split by classification levels">
                <div className="h-44 flex items-end justify-around pb-4 pt-2">
                  <div className="flex flex-col items-center gap-2 w-16">
                    <div className="text-sm font-semibold text-white">{stats.critical}</div>
                    <div
                      className="w-8 bg-red-500/70 border border-red-500 rounded-t-md transition-all duration-500 shadow-glow-red"
                      style={{ height: `${Math.max(4, (stats.critical / filteredNodes.length) * 100)}px` }}
                    />
                    <div className="text-[10px] text-muted uppercase">CRITICAL</div>
                  </div>

                  <div className="flex flex-col items-center gap-2 w-16">
                    <div className="text-sm font-semibold text-white">{stats.warning}</div>
                    <div
                      className="w-8 bg-yellow-500/70 border border-yellow-500 rounded-t-md transition-all duration-500 shadow-glow-yellow"
                      style={{ height: `${Math.max(4, (stats.warning / filteredNodes.length) * 100)}px` }}
                    />
                    <div className="text-[10px] text-muted uppercase">WARNING</div>
                  </div>

                  <div className="flex flex-col items-center gap-2 w-16">
                    <div className="text-sm font-semibold text-white">{stats.healthy}</div>
                    <div
                      className="w-8 bg-green-500/70 border border-green-500 rounded-t-md transition-all duration-500"
                      style={{ height: `${Math.max(4, (stats.healthy / filteredNodes.length) * 100)}px` }}
                    />
                    <div className="text-[10px] text-muted uppercase">HEALTHY</div>
                  </div>
                </div>
              </Card>

              <Card title="Model Classifier Confidence" subtitle="Random Forest probability levels across surveyed nodes">
                <div className="h-44 relative">
                  {/* Clean SVG Area Chart */}
                  <svg className="w-full h-full" viewBox="0 0 100 100" preserveAspectRatio="none">
                    <defs>
                      <linearGradient id="chartGlow" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#00d4aa" stopOpacity="0.4" />
                        <stop offset="100%" stopColor="#00d4aa" stopOpacity="0" />
                      </linearGradient>
                    </defs>
                    
                    {/* Gridlines */}
                    <line x1="0" y1="25" x2="100" y2="25" stroke="#1e2a3f" strokeWidth="0.5" strokeDasharray="2,2" />
                    <line x1="0" y1="50" x2="100" y2="50" stroke="#1e2a3f" strokeWidth="0.5" strokeDasharray="2,2" />
                    <line x1="0" y1="75" x2="100" y2="75" stroke="#1e2a3f" strokeWidth="0.5" strokeDasharray="2,2" />

                    {/* Area under line */}
                    <path
                      d={
                        filteredNodes.length > 1
                          ? `M 0 100 ` +
                            filteredNodes
                              .map(([_, r], idx) => {
                                const rfConf = (r.anomaly as any)?.rf_confidence ?? 0
                                const x = (idx / (filteredNodes.length - 1)) * 100
                                const y = 100 - rfConf * 100
                                return `L ${x} ${y}`
                              })
                              .join(' ') +
                            ` L 100 100 Z`
                          : 'M 0 100 L 100 100 Z'
                      }
                      fill="url(#chartGlow)"
                    />

                    {/* Glowing Stroke Path */}
                    <path
                      d={
                        filteredNodes.length > 1
                          ? filteredNodes
                              .map(([_, r], idx) => {
                                const rfConf = (r.anomaly as any)?.rf_confidence ?? 0
                                const x = (idx / (filteredNodes.length - 1)) * 100
                                const y = 100 - rfConf * 100
                                return `${idx === 0 ? 'M' : 'L'} ${x} ${y}`
                              })
                              .join(' ')
                          : 'M 0 100 L 100 100'
                      }
                      fill="none"
                      stroke="#00d4aa"
                      strokeWidth="2.5"
                    />
                  </svg>
                  <div className="absolute top-0 left-0 p-1 text-[8px] font-mono text-muted">100% CONFIDENCE</div>
                  <div className="absolute bottom-0 left-0 p-1 text-[8px] font-mono text-muted">0%</div>
                </div>
              </Card>
            </div>
          )}
        </div>

        {/* DETAILS INSPECTOR COLUMN */}
        <div className="space-y-6">
          <Card
            title="Diagnostic Inspector"
            subtitle="Deep statistical insights and AI remediation suggestions"
          >
            {inspectorNode ? (
              <div className="space-y-6">
                <div>
                  <h3 className="text-sm font-semibold text-white font-mono">{inspectorNode.node_id}</h3>
                  <p className="text-xs text-muted mt-0.5">Role: compute-node</p>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="p-3 bg-surface3 border border-border/80 rounded-lg">
                    <p className="text-[10px] text-muted">Isolation Forest Score</p>
                    <p className="text-lg font-bold text-white mt-1">
                      {String((inspectorNode.anomaly as any)?.if_score ?? '—')}
                    </p>
                    <p className="text-[8px] text-muted mt-0.5">Deviation threshold limit</p>
                  </div>

                  <div className="p-3 bg-surface3 border border-border/80 rounded-lg">
                    <p className="text-[10px] text-muted">Random Forest Conf</p>
                    <p className="text-lg font-bold text-white mt-1">
                      {typeof (inspectorNode.anomaly as any)?.rf_confidence === 'number'
                        ? `${Math.round((inspectorNode.anomaly as any).rf_confidence * 100)}%`
                        : '—'}
                    </p>
                    <p className="text-[8px] text-muted mt-0.5">Outlier authenticity</p>
                  </div>
                </div>

                {/* TRIGGERS */}
                <div>
                  <h4 className="text-xs font-semibold text-white uppercase tracking-wider mb-2">Triggers</h4>
                  {inspectorNode.triggers && inspectorNode.triggers.length > 0 ? (
                    <div className="flex flex-wrap gap-1.5">
                      {inspectorNode.triggers.map((t) => (
                        <span
                          key={t}
                          className="px-2.5 py-1 rounded text-xs border border-yellow-500/20 bg-yellow-500/10 text-yellow-300 font-semibold"
                        >
                          {t.replace('if_anomaly:', 'Anomaly Model Flagged: ')}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <div className="flex items-center gap-1.5 text-xs text-green-400 bg-green-500/10 border border-green-500/20 px-3 py-2 rounded-lg">
                      <CheckCircle className="w-3.5 h-3.5" />
                      No rule violations or ML outliers detected.
                    </div>
                  )}
                </div>

                {/* REMEDIATIONS RECOMMENDATION */}
                <div>
                  <h4 className="text-xs font-semibold text-white uppercase tracking-wider mb-2 flex items-center gap-1">
                    <Sparkles className="w-3.5 h-3.5 text-accent animate-pulse" />
                    Remediation Advice
                  </h4>
                  {inspectorNode.recommendations && inspectorNode.recommendations.length > 0 ? (
                    <ul className="space-y-2">
                      {inspectorNode.recommendations.map((rec, i) => (
                        <li
                          key={i}
                          className="text-xs p-3 rounded-lg border border-accent/20 bg-accent-dim/5 text-accent font-medium leading-relaxed"
                        >
                          {rec}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-xs text-muted">Node is stable. No action required.</p>
                  )}
                </div>

                {/* RAW API COMPONENT */}
                <div className="pt-4 border-t border-border/80">
                  <h4 className="text-xs font-semibold text-white uppercase tracking-wider mb-2">Raw API Response</h4>
                  <pre className="text-[10px] bg-surface3 border border-border p-3 rounded-lg overflow-x-auto max-h-48 font-mono text-gray-400">
                    {JSON.stringify(inspectorNode, null, 2)}
                  </pre>
                </div>
              </div>
            ) : (
              <div className="text-center py-12 text-muted">
                <Info className="w-8 h-8 text-faint mx-auto mb-2" />
                <p className="text-xs">Select any node from the heatmap or table to view detailed diagnostics and recommendations.</p>
              </div>
            )}
          </Card>
        </div>
      </div>

      {/* TRAINING CONTROLS */}
      <Card
        title="Model Registry & Training Control"
        subtitle="POST /api/v1/analytics/anomaly/train"
      >
        <div className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-muted mb-1">History Window (Days)</label>
              <input
                type="number"
                value={trainDays}
                onChange={(e) => setTrainDays(e.target.value)}
                className="w-full bg-surface3 border border-border rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-accent/50"
              />
            </div>
            <div>
              <label className="block text-xs text-muted mb-1">Chaos Snapshots</label>
              <input
                type="number"
                value={trainChaosSnaps}
                onChange={(e) => setTrainChaosSnaps(e.target.value)}
                className="w-full bg-surface3 border border-border rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-accent/50"
              />
            </div>
          </div>

          <button
            onClick={handleTrainModels}
            disabled={training || statusLoading}
            className="px-4 py-2 text-sm font-semibold rounded-lg bg-surface3 border border-border text-white hover:bg-surface2 transition disabled:opacity-50 flex items-center gap-2"
          >
            {training ? (
              <>
                <LoadingSpinner label="Training Models..." />
              </>
            ) : (
              <>
                <RefreshCw className="w-3.5 h-3.5" />
                Trigger Calibration Pipeline
              </>
            )}
          </button>
        </div>
      </Card>

      {/* SINGLE SCAN SIMULATOR */}
      <Card
        title="Manual Anomaly Scanner"
        subtitle="POST /api/v1/analytics/anomaly/detect/{node_id}"
      >
        <div className="space-y-4">
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <div className="col-span-2 sm:col-span-3 lg:col-span-1">
              <label className="block text-xs text-muted mb-1">Node ID</label>
              <input
                value={singleNodeId}
                onChange={(e) => setSingleNodeId(e.target.value)}
                className="w-full bg-surface3 border border-border rounded-lg px-3 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-accent/50 font-mono"
              />
            </div>

            <div>
              <label className="block text-xs text-muted mb-1 flex items-center gap-1">
                <Cpu className="w-3 h-3" /> CPU %
              </label>
              <input
                type="number"
                value={mCpu}
                onChange={(e) => setMCpu(e.target.value)}
                className="w-full bg-surface3 border border-border rounded-lg px-3 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-accent/50"
              />
            </div>

            <div>
              <label className="block text-xs text-muted mb-1 flex items-center gap-1">
                <Layers className="w-3 h-3" /> Mem %
              </label>
              <input
                type="number"
                value={mMem}
                onChange={(e) => setMMem(e.target.value)}
                className="w-full bg-surface3 border border-border rounded-lg px-3 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-accent/50"
              />
            </div>

            <div>
              <label className="block text-xs text-muted mb-1 flex items-center gap-1">
                <Database className="w-3 h-3" /> Disk IOPS
              </label>
              <input
                type="number"
                value={mIops}
                onChange={(e) => setMIops(e.target.value)}
                className="w-full bg-surface3 border border-border rounded-lg px-3 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-accent/50"
              />
            </div>

            <div>
              <label className="block text-xs text-muted mb-1 flex items-center gap-1">
                <Zap className="w-3 h-3" /> Power W
              </label>
              <input
                type="number"
                value={mPwr}
                onChange={(e) => setMPwr(e.target.value)}
                className="w-full bg-surface3 border border-border rounded-lg px-3 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-accent/50"
              />
            </div>

            <div>
              <label className="block text-xs text-muted mb-1 flex items-center gap-1">
                <Thermometer className="w-3 h-3" /> Temp °C
              </label>
              <input
                type="number"
                value={mTemp}
                onChange={(e) => setMTemp(e.target.value)}
                className="w-full bg-surface3 border border-border rounded-lg px-3 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-accent/50"
              />
            </div>
          </div>

          {singleScanError && <ErrorBanner message={singleScanError} />}

          <button
            onClick={handleSingleScan}
            disabled={scanningSingle || statusData?.trained === false}
            className="px-4 py-2 text-sm font-semibold rounded-lg bg-surface3 border border-border text-white hover:border-gray-500 transition disabled:opacity-50 flex items-center gap-2"
          >
            {scanningSingle ? (
              <>
                <LoadingSpinner label="Evaluating snapshot..." />
              </>
            ) : (
              <>
                <Play className="w-3.5 h-3.5 fill-current" />
                Run Model Simulation Scan
              </>
            )}
          </button>
        </div>
      </Card>
    </div>
  )
}