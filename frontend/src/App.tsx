import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Topology from './pages/Topology'
import Simulation from './pages/Simulation'
import Drift from './pages/Drift'
import Analytics from './pages/Analytics'
import Reports from './pages/Reports'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="topology" element={<Topology />} />
        <Route path="simulation" element={<Simulation />} />
        <Route path="drift" element={<Drift />} />
        <Route path="analytics" element={<Analytics />} />
        <Route path="reports" element={<Reports />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
