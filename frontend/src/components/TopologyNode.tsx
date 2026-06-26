import { memo } from 'react'
import { Handle, Position, type Node, type NodeProps } from '@xyflow/react'
import { stateBadgeClass } from '../utils/format'

export interface TopologyNodeData extends Record<string, unknown> {
  label: string
  fullId: string
  role: string
  droplet: string
  state: string
}

export type TopologyFlowNode = Node<TopologyNodeData, 'topology'>

// ── Role → visual theme ───────────────────────────────────────────────────────
const ROLE_THEME: Record<
  string,
  { border: string; glow: string; bg: string; accent: string; icon: string }
> = {
  // Network fabric — violet
  'spine-switch':    { border: '#a78bfa', glow: 'rgba(167,139,250,0.4)', bg: '#130f24', accent: '#a78bfa', icon: '⬡' },
  'storage-tor':     { border: '#a78bfa', glow: 'rgba(167,139,250,0.4)', bg: '#130f24', accent: '#a78bfa', icon: '⬡' },
  'tor-router':      { border: '#4d9fff', glow: 'rgba(77,159,255,0.4)',  bg: '#0a1525', accent: '#4d9fff', icon: '⇄' },

  // Compute — teal
  'compute-node':    { border: '#00d4aa', glow: 'rgba(0,212,170,0.35)', bg: '#071a14', accent: '#00d4aa', icon: '▣' },

  // Storage — amber
  'storage-controller': { border: '#f59e0b', glow: 'rgba(245,158,11,0.35)', bg: '#1a1000', accent: '#f59e0b', icon: '⊞' },
  'object-storage':     { border: '#fbbf24', glow: 'rgba(251,191,36,0.3)',  bg: '#161000', accent: '#fbbf24', icon: '⊟' },

  // Observability — fuchsia
  'metrics-collector':  { border: '#e879f9', glow: 'rgba(232,121,249,0.35)', bg: '#170c1f', accent: '#e879f9', icon: '◎' },
  'metrics-dashboard':  { border: '#e879f9', glow: 'rgba(232,121,249,0.35)', bg: '#170c1f', accent: '#e879f9', icon: '▤' },
  'metrics-exporter':   { border: '#c084fc', glow: 'rgba(192,132,252,0.25)', bg: '#120b1c', accent: '#c084fc', icon: '↑' },
  'container-metrics':  { border: '#c084fc', glow: 'rgba(192,132,252,0.25)', bg: '#120b1c', accent: '#c084fc', icon: '⧉' },

  // Management / platform — slate
  'infrastructure-docs': { border: '#94a3b8', glow: 'rgba(148,163,184,0.25)', bg: '#0e1118', accent: '#94a3b8', icon: '📄' },
  'graph-database':      { border: '#7dd3fc', glow: 'rgba(125,211,252,0.3)',  bg: '#071520', accent: '#7dd3fc', icon: '◈' },
  middleware:            { border: '#94a3b8', glow: 'rgba(148,163,184,0.25)', bg: '#0e1118', accent: '#94a3b8', icon: '⇌' },
}

function roleTheme(role: string) {
  return (
    ROLE_THEME[role] ?? {
      border: '#00d4aa',
      glow: 'rgba(0,212,170,0.2)',
      bg: '#0a1117',
      accent: '#00d4aa',
      icon: '●',
    }
  )
}

// ── Node component ────────────────────────────────────────────────────────────
function TopologyNodeComponent({ data, selected }: NodeProps<TopologyFlowNode>) {
  const nd = data
  const theme = roleTheme(nd.role)
  const isAlert = nd.state === 'critical' || nd.state === 'warning'
  const borderColor = isAlert ? '#f87171' : theme.border
  const glowColor   = isAlert ? 'rgba(248,113,113,0.4)' : theme.glow
  const accentColor = isAlert ? '#f87171' : theme.accent

  return (
    <div
      className="relative flex flex-col items-center"
      style={{ width: 152 }}
    >
      <Handle
        type="target"
        position={Position.Top}
        style={{ background: borderColor, width: 8, height: 8, border: 'none', top: -4 }}
      />

      {/* Card */}
      <div
        style={{
          position: 'relative',
          width: '100%',
          background: theme.bg,
          border: `1.5px solid ${borderColor}`,
          borderRadius: 8,
          boxShadow: selected
            ? `0 0 0 2px ${borderColor}, 0 0 18px ${glowColor}`
            : `0 0 8px ${glowColor}`,
          overflow: 'hidden',
        }}
      >
        {/* Left accent bar */}
        <div
          style={{
            position: 'absolute',
            left: 0,
            top: 0,
            bottom: 0,
            width: 3,
            background: accentColor,
            opacity: 0.9,
          }}
        />

        {/* Inner content */}
        <div style={{ paddingLeft: 10, paddingRight: 8, paddingTop: 7, paddingBottom: 7 }}>
          {/* Icon + label row */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <span
              style={{
                fontSize: 13,
                lineHeight: 1,
                color: accentColor,
                flexShrink: 0,
                fontFamily: 'monospace',
              }}
            >
              {theme.icon}
            </span>
            <span
              style={{
                fontSize: 12,
                fontWeight: 600,
                color: '#f1f5f9',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                lineHeight: 1.2,
              }}
              title={nd.fullId}
            >
              {nd.label}
            </span>
          </div>

          {/* Role pill */}
          <div
            style={{
              marginTop: 4,
              fontSize: 9,
              color: accentColor,
              opacity: 0.85,
              letterSpacing: '0.04em',
              textTransform: 'uppercase',
              fontFamily: 'ui-monospace, monospace',
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
            }}
          >
            {nd.role.replace(/-/g, ' ')}
          </div>
        </div>

        {/* Status bar at bottom */}
        <div
          style={{
            height: 3,
            background: isAlert
              ? '#f87171'
              : nd.state === 'healthy' || nd.state === 'active' || nd.state === 'online'
              ? '#00d4aa'
              : nd.state === 'degraded'
              ? '#f59e0b'
              : '#475569',
          }}
        />
      </div>

      {/* State badge */}
      <span
        className={`badge capitalize ${stateBadgeClass(nd.state)}`}
        style={{ fontSize: 9, marginTop: 3 }}
      >
        {nd.state}
      </span>

      <Handle
        type="source"
        position={Position.Bottom}
        style={{ background: borderColor, width: 8, height: 8, border: 'none', bottom: -4 }}
      />
    </div>
  )
}

export default memo(TopologyNodeComponent)